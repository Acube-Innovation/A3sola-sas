# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A project page: one summary card, then the task board.

The card says who the job is for, the facts a person working it reaches for - connection,
system, loan, offer - and how far it has got. The board has a column per party the work is done
with - the company, the PM Surya Ghar portal, KSEB and, for a financed job, the bank - and a
small card per task in plan order, carrying its status and dates.
"""

import frappe
from frappe.utils import cint, flt, fmt_money, format_date, quote

from a3_sola.api import payment_tasks
from a3_sola.api.portal_fields import link_title
from a3_sola.www.a3solaportal.collections import SLUG_OF_DOCTYPE, desk_route, initials, record_route

#: Board columns: (heading, template activity scope, icon), in the order the work starts -
#: after the order, the first step is registering on the PM Surya Ghar portal, where the
#: scheme's work is done, so its column comes before KSEB's.
BOARD_COLUMNS = (
	("Company Activity", "Company Activity", "briefcase"),
	("PM Surya Ghar", "Scheme Activity", "globe"),
	("KSEB Activity", "KSEB Activity", "bolt"),
	("Bank Activity", "Bank Activity", "bank"),
)
#: The column a job shows only when it is financed: without a loan there is no bank work.
FINANCED_ONLY = "Bank Activity"
#: Loan tasks in other columns, likewise left off the board of a job without a loan.
FINANCED_ONLY_TASKS = {"ACPT", "DAL"}


#: The icon for a task, by the document it is carried out in - the same icons the menu uses.
TASK_ICONS = {
	"Sales Order": "cart",
	"Statutory Fee Payment": "cash",
	"Portal Application": "globe",
	"Loan Application": "bank",
	"Solar Agreement": "scroll",
	"Installation Work Order": "wrench",
	"Purchase Order": "box",
	"Delivery Note": "truck",
	"Material Dispatch Notice": "package",
	"Document Pack": "stack",
	"Commissioning Report": "bolt",
	"Customer Review": "star",
	"Subsidy Claim": "wallet",
}
#: Tasks worked as a generic Installation Task, by code; anything else gets the checklist.
GENERIC_TASK_ICONS = {
	"FRM1": "doc", "ADV": "cash", "BAL": "cash", "DSGN": "pen", "SDSGN": "pen", "SPROC": "box", "PROC": "box", "ACPT": "doc", "DAL": "doc",
	"PORTUPD": "globe", "KTST": "gauge", "MTR": "gauge",
}


def hides_money(doc):
	"""Whether the customer's price and payments are kept from this user: a contractor's, who
	is paid by the company - unless the job is also his own sale, as a dealer who installs."""
	from a3_sola.api.partner_scope import partner_kinds

	kinds = partner_kinds()
	if "contractor" not in kinds:
		return False
	if "dealer" not in kinds:
		return True
	from a3_sola.api.partner_scope import _kind_condition

	sold = _kind_condition("dealer", frappe.session.user, "Solar Installation")
	return not (sold and frappe.db.sql(f"select 1 from `tabSolar Installation` where `name` = %s and ({sold})", doc.name))


def project_overview(doc):
	from a3_sola.api import billing
	from a3_sola.api.partner_scope import partner_kind

	consumer, electricity = _consumer_box(doc), _electricity_box(doc)
	solar, proposal = _solar_box(doc), _proposal_box(doc)
	return {
		"consumer": consumer,
		"solar": solar,
		"summary": _summary(consumer, electricity, solar, proposal) + [_location(doc)],
		# The payment schedule: milestones, payments received, what is pending (api/billing).
		# Not the contractor's to see - he is paid by the company, not by the customer.
		"payments": None if hides_money(doc) else billing.schedule(doc),
		"half_paid": _half_paid(doc),
		"columns": _task_columns(doc),
	}


def _half_paid(doc):
	"""The 50% payment rule as the board states it: what is received, whether the held work may
	go ahead, who exempted the job and why, and whether this person may exempt it."""
	from a3_sola.api import stages
	from a3_sola.setup.seed_stages import HALF_PAID_PERCENT, HALF_PAID_TASKS

	held = [r for r in doc.stages if r.stage_code in HALF_PAID_TASKS and r.status in ("Pending", "Skipped")]
	share = stages.paid_share(doc)
	return {
		"percent": HALF_PAID_PERCENT,
		"share": "{0:g}".format(share),
		"open": bool(doc.get("half_payment_exempt")) or share >= HALF_PAID_PERCENT,
		"exempt": bool(doc.get("half_payment_exempt")),
		"exempt_by": (frappe.db.get_value("User", doc.half_payment_exempt_by, "full_name") or doc.half_payment_exempt_by)
		if doc.get("half_payment_exempt_by") else "",
		"exempt_reason": doc.get("half_payment_exempt_reason") or "",
		"waiting": len(held),
		"can_exempt": bool(set(stages.MANAGER_ROLES) & set(frappe.get_roles())) and bool(doc.has_permission("write")),
	}


def _location(doc):
	"""The site, as a link that opens Google Maps directions to it."""
	from a3_sola.api import documents, purchase_list

	point = purchase_list.location(doc)
	if not point:
		return {"label": "Location", "ic": "pin", "value": ""}
	return {"label": "Location", "ic": "pin", "value": "{0:.4f}, {1:.4f} ↗".format(*point), "route": documents.maps_link(*point),
		"external": True}


def _summary(consumer, electricity, solar, proposal):
	"""The one card above the board: the facts a person working the job reaches for, taken
	from the consumer, connection, system and offer - each said once, with its icon."""
	facts = dict(consumer["facts"])
	connection = dict(electricity["facts"])
	system = " ".join(filter(None, [f"{solar['capacity']} kW" if solar["capacity"] else "", solar["system_type"]]))
	loan = " · ".join(filter(None, [proposal["loan"], proposal["lender"]]))
	return [
		{"label": "Consumer No.", "ic": "barcode", "value": facts.get("Consumer No.")},
		{"label": "Mobile", "ic": "phone", "value": facts.get("Mobile")},
		{"label": "DISCOM Section", "ic": "globe", "value": connection.get("Section")},
		{"label": "Connection", "ic": "power", "value": connection.get("Connection")},
		{"label": "System", "ic": "bolt", "value": system},
		{"label": "Package", "ic": "package", "value": solar["package"]},
		{"label": "Modules", "ic": "stack", "value": solar["modules"]},
		{"label": "Inverter", "ic": "transfer", "value": solar["inverters"]},
		{"label": "Subsidy Scheme", "ic": "shield", "value": connection.get("Subsidy Scheme")},
		{"label": "Loan", "ic": "bank", "value": loan},
		{"label": "Proposal", "ic": "doc", "value": proposal["name"], "route": proposal["route"], "badge": proposal["status"]},
		{"label": "Net Cost", "ic": "wallet", "value": proposal["net_cost"]},
	]


def _route(doctype, name):
	if not name:
		return ""
	if doctype in SLUG_OF_DOCTYPE:
		return record_route(SLUG_OF_DOCTYPE[doctype], name)
	return desk_route(doctype, name)


def _date(value):
	return format_date(value, "dd MMM yyyy") if value else ""


def _money(value):
	return fmt_money(value) if flt(value) else ""


def _consumer_box(doc):
	photo = (
		frappe.db.get_value("Solar Consumer", doc.solar_consumer, "consumer_photo") if doc.solar_consumer else None
	)
	name = doc.consumer_name or doc.lead_name or doc.name
	return {
		"name": name,
		"photo": photo or "",
		"initials": initials(name),
		"route": _route("Solar Consumer", doc.solar_consumer),
		"facts": [
			("Consumer No.", doc.consumer_number),
			("Mobile", doc.consumer_mobile or doc.lead_mobile),
			("Email", doc.consumer_email),
			("Category", doc.consumer_category),
			("KYC", doc.consumer_kyc_status),
			("Lead", doc.lead_name or doc.lead),
		],
	}


def _electricity_box(doc):
	load = "{0:g} kW".format(flt(doc.sanctioned_load_kw, 3)) if flt(doc.sanctioned_load_kw) else ""
	connected = "{0:g} W".format(flt(doc.connected_load_watts)) if flt(doc.connected_load_watts) else ""
	units = "{0:g}".format(flt(doc.consumer_avg_units, 2)) if flt(doc.consumer_avg_units) else ""
	return {
		"discom": link_title("DISCOM", doc.consumer_discom),
		"facts": [
			("Section", link_title("DISCOM Section", doc.consumer_discom_section)),
			("Connection", doc.consumer_connection_type),
			("Tariff", doc.tariff_category),
			("Sanctioned Load", load),
			("Connected Load", connected),
			("Avg Units", units),
			("Avg Bill", _money(doc.consumer_avg_bill)),
			("Subsidy Scheme", link_title("Subsidy Scheme", doc.lead_subsidy_scheme)),
		],
		"eligibility": doc.eligibility_result or "",
		"eligibility_slug": (doc.eligibility_result or "").lower().replace(" ", "-"),
	}


def _solar_box(doc):
	if doc.panels:
		panel = doc.panels[0]
		count = sum(cint(r.nos) for r in doc.panels) or doc.module_count
		modules = _component_line(count, panel.panel_capacity_wp, "Wp", panel.panel_make)
	else:
		modules = _component_line(doc.module_count, doc.module_wattage, "Wp", doc.module_make)
	if doc.inverters:
		inverter = doc.inverters[0]
		count = sum(cint(r.nos) for r in doc.inverters) or 1
		inverters = _component_line(count, inverter.inverter_capacity_kw, "kW", inverter.inverter_make)
	else:
		inverters = _component_line(1 if doc.inverter_make else 0, doc.inverter_capacity_kw, "kW", doc.inverter_make)

	live = [r for r in doc.stages if r.status != "Skipped"]
	done = len([r for r in live if r.status == "Completed"])
	return {
		"capacity": "{0:g}".format(flt(doc.capacity_kw, 3)) if flt(doc.capacity_kw) else "",
		"system_type": doc.system_type,
		"package": link_title("Solar Package", doc.solar_package),
		"modules": modules,
		"inverters": inverters,
		"status": doc.status,
		"status_slug": (doc.status or "").lower().replace(" ", "-"),
		"percent": int(round(flt(doc.overall_progress_percent))),
		"done": done,
		"total": len(live),
		"focus": doc.current_stage,
		"days": cint(doc.days_since_order),
		"start": _date(doc.execution_start_date or doc.order_date),
		"overdue": bool(doc.is_sla_breached),
	}


def _component_line(count, rating, unit, make):
	if not (count or rating or make):
		return ""
	parts = []
	if count and rating:
		parts.append("{0} × {1:g} {2}".format(cint(count), flt(rating), unit))
	elif rating:
		parts.append("{0:g} {1}".format(flt(rating), unit))
	if make:
		parts.append(link_title("Component Make", make))
	return " · ".join(parts)


def _proposal_box(doc):
	from a3_sola.api.partner_scope import partner_kind

	# The customer's price is no business of the installation contractor's.
	money = (lambda value: "") if hides_money(doc) else _money
	return {
		"name": doc.solar_proposal or "",
		"route": _route("Solar Proposal", doc.solar_proposal),
		"status": doc.proposal_status or "",
		"status_slug": (doc.proposal_status or "").lower().replace(" ", "-"),
		"estimate": doc.solar_design_estimate or "",
		"estimate_route": _route("Solar Design Estimate", doc.solar_design_estimate),
		"facts": [
			("Proposed Size", "{0:g} kW".format(flt(doc.estimate_capacity_kw, 3)) if flt(doc.estimate_capacity_kw) else ""),
			("Proposal Date", _date(doc.proposal_date)),
			("Project Cost", money(doc.estimate_project_cost)),
			("Subsidy", money(doc.estimate_subsidy)),
		],
		"net_cost": money(doc.estimate_net_cost),
		# The job's own Financed (the lead's answer as quoted, editable on the project), not
		# the lead's first answer.
		"loan": "Yes" if doc.is_financed else ("No" if doc.loan_required or doc.quotation else ""),
		"lender": (doc.lender or doc.quoted_lender or "") if doc.is_financed else "",
	}


def _task_columns(doc):
	"""A column per party, each with its tasks in plan order. A job that is not financed has
	no bank column, and its loan tasks (skipped, as Financed Sales Only) are not shown."""
	shown = [c for c in BOARD_COLUMNS if doc.is_financed or c[1] != FINANCED_ONLY]
	columns = [
		{"label": label, "icon": icon, "key": frappe.scrub(label).replace("_", "-"), "tasks": []}
		for label, _scope, icon in shown
	]
	index = {scope: i for i, (_label, scope, _icon) in enumerate(shown)}
	people = {}
	# Shown by name: a row saved without its fetched name takes the user's own.
	unnamed = list({a.user for a in doc.get("task_assignees") or [] if a.user and not a.full_name})
	names = dict(frappe.get_all("User", filters={"name": ["in", unnamed]}, fields=["name", "full_name"],
		as_list=True)) if unnamed else {}
	for a in doc.get("task_assignees") or []:
		people.setdefault(a.stage_code, []).append({"user": a.user, "name": a.full_name or names.get(a.user) or a.user})
	from a3_sola.api.tasks import may_complete

	from a3_sola.api import stages
	from a3_sola.setup.seed_stages import HALF_PAID_TASKS

	half_open = stages.half_paid_open(doc)
	for row in doc.stages:
		if not doc.is_financed and (row.activity_scope == FINANCED_ONLY or row.stage_code in FINANCED_ONLY_TASKS):
			continue
		task = _task(row, doc.name)
		# Held for 50% payment: shown, but not opened or completed until half is in (or exempt).
		task["locked"] = (not half_open and row.stage_code in HALF_PAID_TASKS and row.status in ("Pending", "Skipped"))
		if task["locked"]:
			task["reason"] = stages.half_paid_lock(doc, row.stage_code) or task["reason"]
		task["assignees"] = people.get(row.stage_code, [])
		task["contractor"] = _contractor(row)
		# Completed straight from the board, with a remark, by its assignee or a manager.
		task["can_complete"] = (not task["locked"] and row.status not in ("Completed", "Skipped")
			and may_complete(doc, row.stage_code))
		# A task the template has not scoped yet is the company's own until it says otherwise.
		columns[index.get(row.activity_scope, 0)]["tasks"].append(task)
	for column in columns:
		live = [t for t in column["tasks"] if t["status"] != "Skipped"]
		column["total"] = len(live)
		column["done"] = len([t for t in live if t["status"] == "Completed"])
	return columns


def _contractor(row):
	"""The contractor a work order task is with, once its work order names one - a
	contractor has no login, so the task itself is the Project Engineer's."""
	if row.task_doctype != "Installation Work Order" or not row.task_document:
		return ""
	contractor = frappe.db.get_value("Installation Work Order", row.task_document, "solar_contractor")
	return link_title("Solar Contractor", contractor) if contractor else ""


def _task(row, installation=None):
	"""One task card. With the job's `installation`, the card opens a menu: the task where it
	is carried out (projects/task.py) - a skipped task with nothing done on it has nowhere to
	go - its documents, and skipping it or putting it back."""
	open_ = row.status not in ("Completed", "Skipped")
	return {
		"code": row.stage_code,
		"name": row.stage_name,
		"icon": TASK_ICONS.get(row.task_doctype) or GENERIC_TASK_ICONS.get(row.stage_code, "checklist"),
		# A payment marked received waits for Accounts to confirm it (api/payment_tasks).
		"status": payment_tasks.AWAITING if payment_tasks.awaiting(row) else row.status,
		"status_slug": (payment_tasks.AWAITING if payment_tasks.awaiting(row) else row.status or "").lower().replace(" ", "-"),
		"plan": " – ".join(filter(None, [
			format_date(row.planned_start_date, "dd MMM") if row.planned_start_date else "",
			format_date(row.planned_date, "dd MMM") if row.planned_date else "",
		])),
		"due": format_date(row.due_date, "dd MMM") if row.due_date and open_ else "",
		"completed": format_date(row.actual_completion_date, "dd MMM") if row.status == "Completed" and row.actual_completion_date else "",
		"overdue": bool(row.is_sla_breached),
		"document": row.task_document or "",
		"document_route": _route(row.task_doctype, row.task_document) if row.task_document else "",
		"reason": row.skip_reason or row.blocked_reason or "",
		"url": "{0}/tasks/{1}".format(record_route("projects", installation), quote(row.stage_code))
		if installation and row.stage_code and (row.status != "Skipped" or row.task_document) else "",
		# The card's menu (portal_project_board.js) works any task of the job, skipped too.
		"menu": bool(installation and row.stage_code),
		"mandatory": bool(row.is_mandatory),
	}
