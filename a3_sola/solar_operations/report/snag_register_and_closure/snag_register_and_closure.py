# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Snag Register & Closure.

Repeat-category analysis identifies a systemic quality problem before it becomes a
portfolio problem - and an unresolved defect is a registration risk."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Snag"), "fieldname": "name", "fieldtype": "Link", "options": "Installation Snag", "width": 140},
		{"label": _("Installation"), "fieldname": "solar_installation", "fieldtype": "Link", "options": "Solar Installation", "width": 150},
		{"label": _("Severity"), "fieldname": "severity", "fieldtype": "Data", "width": 100},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 170},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Reported"), "fieldname": "reported_on", "fieldtype": "Date", "width": 100},
		{"label": _("Target"), "fieldname": "target_closure_date", "fieldtype": "Date", "width": 100},
		{"label": _("Age (days)"), "fieldname": "age", "fieldtype": "Int", "width": 100},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Check", "width": 90},
		{"label": _("Assigned"), "fieldname": "assigned_to", "fieldtype": "Link", "options": "User", "width": 150},
	]


def get_data(filters):
	conditions = {"company": filters.company, "docstatus": ["<", 2]}
	if not filters.get("include_closed"):
		conditions["status"] = ["in", ["Open", "In Progress"]]
	rows = frappe.get_list(
		"Installation Snag",
		filters=conditions,
		fields=[
			"name", "solar_installation", "severity", "category", "source", "status",
			"reported_on", "target_closure_date", "assigned_to", "resolved_on",
		],
		limit_page_length=0,
	)
	for row in rows:
		end = getdate(row.resolved_on) if row.resolved_on else getdate(today())
		row["age"] = date_diff(end, getdate(row.reported_on)) if row.reported_on else 0
		row["overdue"] = (
			1
			if row.target_closure_date and not row.resolved_on
			and getdate(row.target_closure_date) < getdate(today())
			else 0
		)
	return sorted(rows, key=lambda r: (-r["overdue"], -r["age"]))
