# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Demo Request Pipeline.

Grouped by status with the age of the oldest request in each. Time to first contact is the
number a sales manager should read first: a demo request answered on day three is usually
a demo request answered by a competitor on day one.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, time_diff_in_hours

STATUS_ORDER = (
	"New", "Contacted", "Demo Scheduled", "Demo Completed", "Converted",
	"Not Interested", "Spam",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
		{"label": _("Requests"), "fieldname": "count", "fieldtype": "Int", "width": 110},
		{"label": _("Unassigned"), "fieldname": "unassigned", "fieldtype": "Int", "width": 130},
		{"label": _("Oldest (days)"), "fieldname": "oldest_days", "fieldtype": "Int", "width": 140},
		{"label": _("Avg Hours to First Contact"), "fieldname": "avg_first_contact", "fieldtype": "Float", "precision": 1, "width": 210},
		{"label": _("Overdue Follow-ups"), "fieldname": "overdue", "fieldtype": "Int", "width": 170},
	]


def get_data(filters):
	conditions = {}
	if filters.get("assigned_to"):
		conditions["assigned_to"] = filters.assigned_to
	rows = frappe.get_all(
		"Demo Request",
		filters=conditions,
		fields=["status", "assigned_to", "creation", "first_contacted_on", "follow_up_date"],
		limit_page_length=0,
	)
	grouped = {}
	today = frappe.utils.getdate()
	for row in rows:
		bucket = grouped.setdefault(
			row.status or "New",
			{"status": row.status or "New", "count": 0, "unassigned": 0, "oldest_days": 0,
			 "_hours": 0.0, "_contacted": 0, "overdue": 0},
		)
		bucket["count"] += 1
		bucket["unassigned"] += 0 if row.assigned_to else 1
		bucket["oldest_days"] = max(
			bucket["oldest_days"], frappe.utils.date_diff(today, frappe.utils.getdate(row.creation))
		)
		if row.first_contacted_on:
			bucket["_hours"] += flt(
				time_diff_in_hours(get_datetime(row.first_contacted_on), get_datetime(row.creation))
			)
			bucket["_contacted"] += 1
		if row.follow_up_date and frappe.utils.getdate(row.follow_up_date) < today:
			bucket["overdue"] += 1

	out = []
	for status in STATUS_ORDER:
		bucket = grouped.get(status)
		if not bucket:
			continue
		contacted = bucket.pop("_contacted")
		bucket["avg_first_contact"] = flt(bucket.pop("_hours") / contacted, 1) if contacted else 0.0
		out.append(bucket)
	return out
