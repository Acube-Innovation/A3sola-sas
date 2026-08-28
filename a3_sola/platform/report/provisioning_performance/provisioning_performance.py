# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Provisioning Performance.

Success rate, duration and - the useful column - which step fails most. Provisioning
is a pipeline, and a pipeline's problem is always one step rather than the whole of it."""

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Step"), "fieldname": "step", "fieldtype": "Data", "width": 260},
		{"label": _("Runs"), "fieldname": "runs", "fieldtype": "Int", "width": 90},
		{"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 110},
		{"label": _("Failed"), "fieldname": "failed", "fieldtype": "Int", "width": 90},
		{"label": _("Failure Rate"), "fieldname": "failure_rate", "fieldtype": "Percent", "width": 120},
		{"label": _("Average Seconds"), "fieldname": "average_seconds", "fieldtype": "Float", "width": 140},
		{"label": _("Slowest"), "fieldname": "slowest", "fieldtype": "Float", "width": 110},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Provisioning Step Log",
		filters={"parenttype": "Provisioning Job"},
		fields=["step_code", "step_name", "status", "duration_seconds"],
		limit_page_length=0,
	)
	buckets = {}
	for row in rows:
		bucket = buckets.setdefault(
			row.step_code,
			{"step": f"{row.step_code} - {row.step_name}", "runs": 0, "completed": 0,
			 "failed": 0, "total_seconds": 0.0, "slowest": 0.0},
		)
		if row.status in ("Pending",):
			continue
		bucket["runs"] += 1
		if row.status == "Completed":
			bucket["completed"] += 1
		elif row.status == "Failed":
			bucket["failed"] += 1
		seconds = flt(row.duration_seconds)
		bucket["total_seconds"] += seconds
		bucket["slowest"] = max(bucket["slowest"], seconds)

	out = []
	for code in sorted(buckets):
		bucket = buckets[code]
		runs = bucket["runs"] or 1
		out.append(
			{
				"step": bucket["step"],
				"runs": bucket["runs"],
				"completed": bucket["completed"],
				"failed": bucket["failed"],
				"failure_rate": round(bucket["failed"] * 100.0 / runs, 1),
				"average_seconds": round(bucket["total_seconds"] / runs, 2),
				"slowest": round(bucket["slowest"], 2),
			}
		)
	return out
