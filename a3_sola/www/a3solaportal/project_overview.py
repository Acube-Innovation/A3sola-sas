# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A project page: its lead as a row, four boxes, then the task board.

The boxes answer who the job is for, what their connection is, what is being built and how
far it has got, and what was offered. The board has a column per party the work is done
with - the company, the DISCOM, the KSEB portal side and the bank - and a small card per
task in plan order, carrying its status and dates.
"""

import frappe
from frappe.utils import cint, flt, fmt_money, format_date

from a3_sola.api.portal_fields import link_title
from a3_sola.www.a3solaportal.collections import SLUG_OF_DOCTYPE, desk_route, initials, record_route

#: Board columns: (heading, template activity scope, icon). KSEB is the DISCOM, so its tasks
#: read as DISCOM activity; the PM Surya Ghar scheme work is done on the KSEB side.
BOARD_COLUMNS = (
	("Company Activity", "Company Activity", "briefcase"),
	("DISCOM Activity", "KSEB Activity", "bolt"),
	("KSEB Activity", "Scheme Activity", "globe"),
	("Bank Activity", "Bank Activity", "bank"),
)


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
	"FRM1": "doc", "ADV": "cash", "BAL": "cash", "DSGN": "pen", "CCERT": "shield",
	"PORTUPD": "globe", "KTST": "gauge", "MTR": "gauge",
}


def project_overview(doc):
	return {
		"lead": _lead_row(doc),
		"consumer": _consumer_box(doc),
		"electricity": _electricity_box(doc),
		"solar": _solar_box(doc),
		"proposal": _proposal_box(doc),
		"columns": _task_columns(doc),
	}


def _lead_row(doc):
	"""The job's lead, as the Leads list shows it: who, contact, status, and who holds it.

	Read with the caller's permissions, so a lead the person may not see is simply left out.
	"""
	if not doc.lead:
		return None
	from a3_sola.www.a3solaportal.leads.index import lead_rows

	rows = lead_rows({"name": doc.lead}, limit=1)
	return rows[0] if rows else None


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
			("Project Cost", _money(doc.estimate_project_cost)),
			("Subsidy", _money(doc.estimate_subsidy)),
		],
		"net_cost": _money(doc.estimate_net_cost),
		"loan": doc.loan_required or "",
		"lender": doc.quoted_lender if doc.loan_required == "Yes" else "",
	}


def _task_columns(doc):
	"""A column per party, each with its tasks in plan order."""
	columns = [
		{"label": label, "icon": icon, "key": frappe.scrub(label).replace("_", "-"), "tasks": []}
		for label, _scope, icon in BOARD_COLUMNS
	]
	index = {scope: i for i, (_label, scope, _icon) in enumerate(BOARD_COLUMNS)}
	for row in doc.stages:
		# A task the template has not scoped yet is the company's own until it says otherwise.
		columns[index.get(row.activity_scope, 0)]["tasks"].append(_task(row))
	for column in columns:
		live = [t for t in column["tasks"] if t["status"] != "Skipped"]
		column["total"] = len(live)
		column["done"] = len([t for t in live if t["status"] == "Completed"])
	return columns


def _task(row):
	open_ = row.status not in ("Completed", "Skipped")
	return {
		"code": row.stage_code,
		"name": row.stage_name,
		"icon": TASK_ICONS.get(row.task_doctype) or GENERIC_TASK_ICONS.get(row.stage_code, "checklist"),
		"status": row.status,
		"status_slug": (row.status or "").lower().replace(" ", "-"),
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
	}
