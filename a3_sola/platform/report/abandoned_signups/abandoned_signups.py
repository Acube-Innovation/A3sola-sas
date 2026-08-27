# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Abandoned Signups.

People who started and never confirmed their email. Most are a mistyped address or a
verification mail in a spam folder, which is a phone call, not a lost lead - so this
carries the contact details rather than just a count.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

from a3_sola.api.settings import get_int


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Signup"), "fieldname": "name", "fieldtype": "Link", "options": "Subscription Signup", "width": 160},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 200},
		{"label": _("Contact"), "fieldname": "full_name", "fieldtype": "Data", "width": 150},
		{"label": _("Email"), "fieldname": "work_email", "fieldtype": "Data", "width": 220},
		{"label": _("Phone"), "fieldname": "phone", "fieldtype": "Data", "width": 130},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 100},
		{"label": _("Value"), "fieldname": "total_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Days Waiting"), "fieldname": "days_waiting", "fieldtype": "Int", "width": 130},
		{"label": _("Resends"), "fieldname": "resends", "fieldtype": "Int", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 180},
	]


def get_data(filters):
	window = int(filters.get("older_than_days") or get_int("signup_abandon_after_days", 7) or 7)
	rows = frappe.get_all(
		"Subscription Signup",
		filters={
			"status": ["in", ["Draft", "Awaiting Email Verification", "Abandoned"]],
			"is_email_verified": 0,
			"docstatus": ["<", 2],
		},
		fields=["name", "organisation_name", "full_name", "work_email", "phone", "plan_code",
		        "total_amount", "creation", "status"],
		limit_page_length=0,
	)
	resends = _resend_counts([r.name for r in rows])
	out = []
	for row in rows:
		row["days_waiting"] = date_diff(today(), getdate(row.creation))
		if row["days_waiting"] < window:
			continue
		row["resends"] = resends.get(row.name, 0)
		row["total_amount"] = flt(row.total_amount, 2)
		out.append(row)
	out.sort(key=lambda r: r["total_amount"], reverse=True)
	return out


def _resend_counts(names):
	if not names:
		return {}
	rows = frappe.get_all(
		"Signup Event Log",
		filters={
			"parent": ["in", names],
			"parenttype": "Subscription Signup",
			"event_type": "Verification Resent",
		},
		fields=["parent", "count(name) as total"],
		group_by="parent",
	)
	return {row.parent: row.total for row in rows}
