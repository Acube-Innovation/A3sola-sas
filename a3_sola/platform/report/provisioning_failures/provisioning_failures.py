# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Provisioning Failures.

Open interventions, oldest first - because the oldest is the customer who has been
waiting longest and does not know why."""

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Job"), "fieldname": "name", "fieldtype": "Link", "options": "Provisioning Job", "width": 140},
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 210},
		{"label": _("Stuck At"), "fieldname": "current_step", "fieldtype": "Data", "width": 210},
		{"label": _("Past the Line"), "fieldname": "past_the_line", "fieldtype": "Data", "width": 120},
		{"label": _("Waiting (hours)"), "fieldname": "age_hours", "fieldtype": "Float", "width": 130},
		{"label": _("Failure"), "fieldname": "failure_summary", "fieldtype": "Data", "width": 400},
	]


def get_data(filters):
	from frappe.utils import now_datetime, time_diff_in_hours

	rows = frappe.get_all(
		"Provisioning Job",
		filters={"requires_manual_intervention": 1, "resolved_on": ["is", "not set"]},
		fields=["name", "tenant", "status", "current_step", "failure_summary", "modified",
		        "point_of_no_return_passed"],
		limit_page_length=0,
	)
	out = []
	for row in rows:
		out.append(
			{
				**row,
				"past_the_line": _("Yes") if cint(row.point_of_no_return_passed) else _("No"),
				"age_hours": round(time_diff_in_hours(now_datetime(), row.modified), 1),
			}
		)
	return sorted(out, key=lambda r: -r["age_hours"])
