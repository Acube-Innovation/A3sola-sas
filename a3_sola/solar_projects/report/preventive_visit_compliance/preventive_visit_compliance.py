# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Preventive Visit Compliance.

Three visits a year for five years is a promise in the client's own scope of work. A missed
visit is a broken promise, and under a scheme-mandated contract it is also a registration
risk - so missed visits are counted, not quietly rescheduled.
"""

import frappe
from frappe import _
from frappe.utils import flt
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Solar OM Contract", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("Planned"), "fieldname": "planned", "fieldtype": "Int", "width": 90},
		{"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": _("Due"), "fieldname": "due", "fieldtype": "Int", "width": 80},
		{"label": _("Missed"), "fieldname": "missed", "fieldtype": "Int", "width": 90},
		{"label": _("Compliance %"), "fieldname": "compliance_percent", "fieldtype": "Percent", "width": 130},
		{"label": _("Scheme Mandated"), "fieldname": "is_scheme_mandated", "fieldtype": "Check", "width": 140},
		{"label": _("Last Technician"), "fieldname": "last_technician", "fieldtype": "Link", "options": "Employee", "width": 160},
		{"label": _("Missed Visits"), "fieldname": "missed_list", "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	contracts = frappe.get_list(
		"Solar OM Contract",
		filters={"company": filters.company, "docstatus": 1},
		fields=["name", "solar_consumer", "is_scheme_mandated"],
		limit_page_length=0,
	)
	if not contracts:
		return []

	names = [c.name for c in contracts]
	counts = frappe.get_all(
		"Solar OM Visit Plan",
		filters={"parent": ["in", names], "parenttype": "Solar OM Contract"},
		fields=["parent", "status", "count(name) as total"],
		group_by="parent, status",
	)
	tally = {}
	for row in counts:
		tally.setdefault(row.parent, {})[row.status] = row.total

	for contract in contracts:
		by_status = tally.get(contract.name, {})
		contract["planned"] = sum(by_status.values())
		contract["completed"] = by_status.get("Completed", 0)
		contract["due"] = by_status.get("Due", 0)
		contract["missed"] = by_status.get("Missed", 0)
		# Only what has actually fallen due can be complied with.
		fallen_due = contract["completed"] + contract["due"] + contract["missed"]
		contract["compliance_percent"] = (
			flt(contract["completed"] * 100.0 / fallen_due, 2) if fallen_due else 100.0
		)
		contract["last_technician"] = frappe.db.get_value(
			"Solar OM Visit", {"om_contract": contract.name, "docstatus": 1}, "technician",
			order_by="visit_date desc",
		)
		# Naming the dates rather than counting them: a manager chasing a missed visit
		# needs to know which month it was.
		missed = frappe.get_all(
			"Solar OM Visit Plan",
			filters={
				"parent": contract.name, "parenttype": "Solar OM Contract", "status": "Missed",
			},
			pluck="scheduled_month",
			order_by="scheduled_date",
		)
		contract["missed_list"] = ", ".join(filter(None, missed))
	contracts.sort(key=lambda c: (c["compliance_percent"], -c["missed"]))
	return contracts
