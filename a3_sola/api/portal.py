# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer portal's data layer.

Read-only, and guarded on every request rather than on the way in. The rule here is that
ownership is re-derived from the logged-in user each time - never taken from a parameter -
so there is no URL to manipulate. A customer sees their own system, their own service
history, their own documents and their own invoices, and nothing financial beyond those:
no cost, no margin, no provision, no subsidy receivable.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from a3_sola.api import calculations

#: What a customer is allowed to see about their own job. Anything absent from this list
#: is absent by decision, not by oversight.
INSTALLATION_FIELDS = (
	"name",
	"consumer_name",
	"consumer_number",
	"capacity_kw",
	"system_type",
	"module_make",
	"module_wattage",
	"module_count",
	"inverter_make",
	"inverter_capacity_kw",
	"spin",
	"discom",
	"discom_section",
	"installation_address",
	"warranty_start_date",
	"warranty_end_date",
)

#: Documents that concern the customer. Everything addressed to them, plus the net
#: metering agreement - which is addressed to the Assistant Engineer but which the customer
#: signs and is entitled to a copy of. Bank and portal paperwork is deliberately absent.
CUSTOMER_RECIPIENTS = ("Consumer",)
CUSTOMER_EXTRA_DOCUMENTS = ("Net Metering Agreement (Stamp Paper)",)


def _customers():
	"""Every Customer the logged-in user is actually linked to.

	Derived from the Contact records that carry their email address, exactly as ERPNext's
	own portal does. A user with no linked customer sees nothing - not an error page and
	not somebody else's system.
	"""
	user = frappe.session.user
	if user in ("Guest", ""):
		return []
	links = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"link_doctype": "Customer",
			"parent": [
				"in",
				frappe.get_all(
					"Contact Email", filters={"email_id": user}, pluck="parent", distinct=True
				)
				or [""],
			],
		},
		pluck="link_name",
		distinct=True,
	)
	linked = frappe.db.get_value("User", user, "name") and frappe.get_all(
		"Portal User", filters={"user": user, "parenttype": "Customer"}, pluck="parent"
	)
	return sorted(set(links) | set(linked or []))


def _owned_installations():
	customers = _customers()
	if not customers:
		return []
	return frappe.get_all(
		"Solar Installation",
		filters={"customer": ["in", customers], "docstatus": 1},
		pluck="name",
	)


def assert_owns(doctype, name):
	"""Re-derive ownership from the session on every request. Never trust a parameter."""
	if not name:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	owned = _owned_installations()
	if doctype == "Solar Installation":
		if name in owned:
			return name
	else:
		installation = frappe.db.get_value(doctype, name, "solar_installation")
		if installation and installation in owned:
			return name
	# Deliberately indistinguishable from a record that does not exist: a different error
	# for "exists but is not yours" would confirm another customer's data.
	frappe.throw(_("Not found"), frappe.DoesNotExistError)


# ------------------------------------------------------------------- the page
def systems():
	"""Every system this customer owns, with its warranty position."""
	out = []
	for name in _owned_installations():
		installation = frappe.db.get_value(
			"Solar Installation", name, INSTALLATION_FIELDS, as_dict=True
		)
		if not installation:
			continue
		installation.update(_commissioning(name))
		installation["warranty"] = warranty_position(name)
		installation["next_visit"] = next_visit(name)
		installation["quoted_band"] = quoted_band(installation.capacity_kw)
		out.append(installation)
	return out


def _commissioning(installation):
	row = frappe.db.get_value(
		"Commissioning Report",
		{"solar_installation": installation, "docstatus": 1},
		["commissioning_date", "net_meter_serial_no", "net_meter_make", "commissioning_certificate_no"],
		as_dict=True,
	)
	return row or {}


def warranty_position(installation):
	"""Warranty end dates by component and make - the question customers actually ask."""
	contract = frappe.db.get_value(
		"Solar OM Contract",
		{"solar_installation": installation, "docstatus": 1},
		[
			"name", "start_date", "end_date", "module_make", "module_product_warranty_years",
			"module_performance_warranty_years", "inverter_make", "inverter_warranty_years",
			"workmanship_warranty_years",
		],
		as_dict=True,
	)
	if not contract:
		return []

	def ends(years):
		return frappe.utils.add_years(getdate(contract.start_date), int(years or 0))

	rows = []
	if contract.module_make:
		make = frappe.db.get_value("Component Make", contract.module_make, "make_name")
		rows.append({
			"component": _("Modules"), "make": make,
			"basis": _("Product"), "years": contract.module_product_warranty_years,
			"ends_on": ends(contract.module_product_warranty_years),
		})
		rows.append({
			"component": _("Modules"), "make": make,
			"basis": _("Performance"), "years": contract.module_performance_warranty_years,
			"ends_on": ends(contract.module_performance_warranty_years),
		})
	if contract.inverter_make:
		rows.append({
			"component": _("Inverter"),
			"make": frappe.db.get_value("Component Make", contract.inverter_make, "make_name"),
			"basis": _("Product"), "years": contract.inverter_warranty_years,
			"ends_on": ends(contract.inverter_warranty_years),
		})
	rows.append({
		"component": _("Workmanship"), "make": None, "basis": _("Installation"),
		"years": contract.workmanship_warranty_years,
		"ends_on": ends(contract.workmanship_warranty_years),
	})
	return rows


def next_visit(installation):
	contract = frappe.db.get_value(
		"Solar OM Contract", {"solar_installation": installation, "docstatus": 1}, "name"
	)
	if not contract:
		return None
	return frappe.db.get_value(
		"Solar OM Visit Plan",
		{
			"parent": contract,
			"parenttype": "Solar OM Contract",
			"status": ["in", ["Scheduled", "Due"]],
			"scheduled_date": [">=", add_days(today(), -1)],
		},
		["scheduled_date", "visit_type"],
		order_by="scheduled_date asc",
		as_dict=True,
	)


def quoted_band(capacity_kw):
	"""What the proposal promised: "20 to 25 units a day for a 5 kW system".

	A complaint almost always starts as "it is not making what you said", so the quoted
	band belongs next to the actual figure rather than in a filing cabinet.
	"""
	band = calculations.estimate_daily_generation_band(capacity_kw)
	return {
		"low": flt(band["low_units_per_day"], 1),
		"high": flt(band["high_units_per_day"], 1),
	}


def generation_history(installation, months=12):
	"""Actual against the design expectation, by reading."""
	assert_owns("Solar Installation", installation)
	rows = frappe.get_all(
		"Generation Reading",
		filters={"solar_installation": installation, "docstatus": 1},
		fields=[
			"reading_date", "units_generated_since_last", "expected_generation_kwh",
			"performance_ratio_percent", "days_since_last_reading",
		],
		order_by="reading_date asc",
		limit_page_length=int(months) + 1,
	)
	for row in rows:
		days = row.days_since_last_reading or 1
		row["actual_units_per_day"] = flt(flt(row.units_generated_since_last) / days, 1)
	return rows


def service_history(installation):
	"""Past visits and the customer's own tickets. No cost figures."""
	assert_owns("Solar Installation", installation)
	contract = frappe.db.get_value(
		"Solar OM Contract", {"solar_installation": installation, "docstatus": 1}, "name"
	)
	if not contract:
		return {"visits": [], "tickets": []}
	return {
		"visits": frappe.get_all(
			"Solar OM Visit",
			filters={"om_contract": contract, "docstatus": 1},
			fields=[
				"name", "visit_date", "visit_type", "items_ok", "items_attention",
				"items_defect", "next_visit_recommendation",
			],
			order_by="visit_date desc",
			limit_page_length=20,
		),
		"tickets": frappe.get_all(
			"Service Ticket",
			filters={"om_contract": contract, "docstatus": 1},
			fields=["name", "reported_on", "category", "severity", "status", "resolved_on"],
			order_by="reported_on desc",
			limit_page_length=20,
		),
	}


def _customer_template_names():
	"""Template records a customer may have a copy of, by name."""
	names = set(
		frappe.get_all(
			"Solar Document Template",
			filters={"recipient": ["in", CUSTOMER_RECIPIENTS]},
			pluck="name",
		)
	)
	names |= set(
		frappe.get_all(
			"Solar Document Template",
			filters={"document_name": ["in", CUSTOMER_EXTRA_DOCUMENTS]},
			pluck="name",
		)
	)
	return names


def documents(installation):
	"""The customer's own copies. Listed without a file URL - see download()."""
	assert_owns("Solar Installation", installation)
	allowed = _customer_template_names()
	if not allowed:
		return []
	rows = frappe.get_all(
		"Generated Document Log",
		filters={
			"parent": installation,
			"parenttype": "Solar Installation",
			"solar_document_template": ["in", list(allowed)],
			"status": ["!=", "Pending"],
		},
		fields=["name", "document_name", "generated_on", "status", "is_stale"],
		order_by="generated_on desc",
	)
	# The file URL is deliberately not returned here. The page renders a name and asks
	# for the URL only when the customer clicks, so no URL is ever sitting in the HTML.
	return rows


def invoices(installation):
	"""Their own invoices, and nothing else financial."""
	assert_owns("Solar Installation", installation)
	project = frappe.db.get_value("Solar Installation", installation, "project")
	if not project:
		return []
	return frappe.get_all(
		"Sales Invoice",
		filters={"project": project, "docstatus": 1},
		fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "status"],
		order_by="posting_date desc",
	)


# ------------------------------------------------------------- guarded actions
@frappe.whitelist()
def download(document_log):
	"""Resolve a document's file URL only after proving the caller owns the job.

	The URL is never rendered into the page. The customer asks for a log row by name,
	ownership is re-derived from the session, and only then is a URL returned - so there
	is no URL in the markup to guess at, and none to share.
	"""
	row = frappe.db.get_value(
		"Generated Document Log",
		document_log,
		["parent", "parenttype", "solar_document_template", "file"],
		as_dict=True,
	)
	if not row or row.parenttype != "Solar Installation":
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	assert_owns("Solar Installation", row.parent)
	if row.solar_document_template not in _customer_template_names():
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	if not row.file:
		frappe.throw(_("This document has not been generated yet."))
	return row.file


@frappe.whitelist()
def raise_ticket(installation, category, description):
	"""Let a customer report a fault against their own system, and only their own."""
	assert_owns("Solar Installation", installation)
	contract = frappe.db.get_value(
		"Solar OM Contract", {"solar_installation": installation, "docstatus": 1}, "name"
	)
	if not contract:
		frappe.throw(_("This system has no active service contract."))
	if not (description or "").strip():
		frappe.throw(_("Please describe what is happening."))

	doc = frappe.get_doc(
		{
			"doctype": "Service Ticket",
			"company": frappe.db.get_value("Solar Installation", installation, "company"),
			"om_contract": contract,
			"reported_on": frappe.utils.now_datetime(),
			"reported_via": "Portal",
			"category": category,
			"description": description,
			"reported_by": frappe.session.user,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
