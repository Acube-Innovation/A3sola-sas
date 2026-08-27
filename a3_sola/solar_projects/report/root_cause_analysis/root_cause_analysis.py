# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Root Cause Analysis.

Cross-tabbed against installation age and the makes actually on the roof, because that is
what identifies a bad batch before it becomes a portfolio problem. Six inverter faults
spread across four makes is ordinary attrition; six on one make, all commissioned in the
same quarter, is a supplier conversation.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

AGE_BANDS = ((365, "Under 1 year"), (730, "1-2 years"), (1825, "2-5 years"), (10**6, "Over 5 years"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Root Cause"), "fieldname": "root_cause", "fieldtype": "Data", "width": 160},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 150},
		{"label": _("Module Make"), "fieldname": "module_make", "fieldtype": "Data", "width": 130},
		{"label": _("Inverter Make"), "fieldname": "inverter_make", "fieldtype": "Data", "width": 130},
		{"label": _("Age at Failure"), "fieldname": "age_band", "fieldtype": "Data", "width": 130},
		{"label": _("Tickets"), "fieldname": "tickets", "fieldtype": "Int", "width": 90},
		{"label": _("Systems Affected"), "fieldname": "systems", "fieldtype": "Int", "width": 140},
		{"label": _("Critical"), "fieldname": "critical", "fieldtype": "Int", "width": 90},
		{"label": _("Reopened"), "fieldname": "reopened", "fieldtype": "Int", "width": 100},
		{"label": _("SLA Breaches"), "fieldname": "breaches", "fieldtype": "Int", "width": 130},
		{"label": _("Avg Hrs to Resolve"), "fieldname": "avg_hours", "fieldtype": "Float", "precision": 1, "width": 160},
		{"label": _("Chargeable Recovered"), "fieldname": "chargeable", "fieldtype": "Currency", "width": 180},
	]


def get_data(filters):
	tickets = frappe.get_list(
		"Service Ticket",
		filters={"company": filters.company, "docstatus": 1, "status": ["in", ["Resolved", "Closed"]]},
		fields=[
			"name", "om_contract", "root_cause", "category", "severity", "reopen_count",
			"resolution_sla_met", "hours_to_resolution", "is_chargeable", "chargeable_amount",
			"reported_on",
		],
		limit_page_length=0,
	)
	if not tickets:
		return []

	context = _contract_context({t.om_contract for t in tickets if t.om_contract})
	grouped = {}
	for ticket in tickets:
		system = context.get(ticket.om_contract, {})
		key = (
			ticket.root_cause or _("Not Recorded"),
			ticket.category,
			system.get("module_make") or _("Unknown"),
			system.get("inverter_make") or _("Unknown"),
			_age_band(system.get("start_date"), ticket.reported_on),
		)
		row = grouped.setdefault(
			key,
			{
				"root_cause": key[0], "category": key[1], "module_make": key[2],
				"inverter_make": key[3], "age_band": key[4],
				"tickets": 0, "critical": 0, "reopened": 0, "breaches": 0,
				"_hours": 0.0, "chargeable": 0.0, "_systems": set(),
			},
		)
		row["tickets"] += 1
		row["critical"] += 1 if ticket.severity == "Critical" else 0
		row["reopened"] += 1 if flt(ticket.reopen_count) else 0
		row["breaches"] += 0 if ticket.resolution_sla_met else 1
		row["_hours"] += flt(ticket.hours_to_resolution)
		row["chargeable"] += flt(ticket.chargeable_amount) if ticket.is_chargeable else 0.0
		row["_systems"].add(ticket.om_contract)

	out = []
	for row in grouped.values():
		row["avg_hours"] = flt(row.pop("_hours") / row["tickets"], 1) if row["tickets"] else 0.0
		row["systems"] = len(row.pop("_systems"))
		out.append(row)
	# A cause hitting many systems outranks one hitting the same system repeatedly.
	out.sort(key=lambda r: (r["systems"], r["tickets"], r["critical"]), reverse=True)
	return out


def _contract_context(contracts):
	if not contracts:
		return {}
	rows = frappe.get_all(
		"Solar OM Contract",
		filters={"name": ["in", list(contracts)]},
		fields=["name", "module_make", "inverter_make", "start_date"],
	)
	makes = {
		row.name: row.make_name
		for row in frappe.get_all("Component Make", fields=["name", "make_name"])
	}
	return {
		row.name: {
			"module_make": makes.get(row.module_make),
			"inverter_make": makes.get(row.inverter_make),
			"start_date": row.start_date,
		}
		for row in rows
	}


def _age_band(commissioned, failed_on):
	if not commissioned:
		return _("Unknown")
	days = date_diff(getdate(failed_on or today()), getdate(commissioned))
	if days < 0:
		return _("Unknown")
	return next(label for limit, label in AGE_BANDS if days <= limit)
