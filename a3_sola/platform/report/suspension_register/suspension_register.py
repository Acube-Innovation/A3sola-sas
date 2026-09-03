# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Suspension Register.

Every suspension, who approved it, how many people it affected and what reversed it - plus
the number that matters most: how long it took from payment arriving to access coming
back. That should be minutes. If it is ever hours, the restoration path has a queue in it
that should not be there.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, time_diff_in_seconds


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, _summary(data)


def get_columns():
	return [
		{"label": _("Suspension"), "fieldname": "name", "fieldtype": "Link", "options": "Access Suspension", "width": 140},
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 140},
		{"label": _("Type"), "fieldname": "suspension_type", "fieldtype": "Data", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 280},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 115},
		{"label": _("Approval"), "fieldname": "approval_status", "fieldtype": "Data", "width": 100},
		{"label": _("Approved By"), "fieldname": "approved_by", "fieldtype": "Link", "options": "User", "width": 160},
		{"label": _("Warned"), "fieldname": "warning_sent_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Applied"), "fieldname": "applied_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Users Disabled"), "fieldname": "users_disabled_count", "fieldtype": "Int", "width": 115},
		{"label": _("Restored"), "fieldname": "restored_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Restored By"), "fieldname": "restoration_trigger", "fieldtype": "Data", "width": 130},
		{"label": _("Blocked For"), "fieldname": "blocked_for", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Access Suspension",
		filters={"docstatus": ["<", 2]},
		fields=["name", "tenant", "suspension_type", "status", "reason",
		        "outstanding_amount", "approval_status", "approved_by", "warning_sent_on",
		        "applied_on", "users_disabled_count", "restored_on", "restoration_trigger"],
		order_by="creation desc",
	)
	for row in rows:
		row["blocked_for"] = _duration(row.applied_on, row.restored_on)
	return rows


def _duration(applied, restored):
	if not (applied and restored):
		return ""
	seconds = time_diff_in_seconds(restored, applied)
	if seconds < 3600:
		return _("{0} min").format(int(seconds // 60))
	if seconds < 86400:
		return _("{0} hr").format(round(seconds / 3600.0, 1))
	return _("{0} days").format(round(seconds / 86400.0, 1))


def _summary(rows):
	applied = [r for r in rows if r.get("applied_on")]
	restored = [r for r in applied if r.get("restored_on")]
	minutes = [
		time_diff_in_seconds(r["restored_on"], r["applied_on"]) / 60.0 for r in restored
	]
	average = round(sum(minutes) / len(minutes), 1) if minutes else 0
	return [
		{"label": _("Applied"), "value": len(applied), "indicator": "Orange"},
		{"label": _("Restored"), "value": len(restored), "indicator": "Green"},
		{"label": _("Still blocked"), "value": len(applied) - len(restored),
		 "indicator": "Red" if len(applied) - len(restored) else "Green"},
		{"label": _("Average time to restore (min)"), "value": average,
		 "indicator": "Green" if average <= 60 else "Red"},
	]
