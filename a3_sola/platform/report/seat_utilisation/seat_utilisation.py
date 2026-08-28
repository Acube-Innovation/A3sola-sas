# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seat Utilisation.

Tenants near or over their quota, and tenants well under it. The first is a
conversation about buying seats; the second is an early churn signal, because a
workspace nobody logs into does not get renewed."""

import frappe
from frappe import _
from frappe.utils import cint, flt


#: Below this share of their seats, a tenant is not really using what they bought.
UNDERUSED = 0.4
#: At or above this, they are about to need more.
NEARLY_FULL = 0.8


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Tenant"), "fieldname": "name", "fieldtype": "Link", "options": "Tenant", "width": 130},
		{"label": _("Organisation"), "fieldname": "tenant_name", "fieldtype": "Data", "width": 200},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 90},
		{"label": _("Quota"), "fieldname": "user_quota", "fieldtype": "Int", "width": 80},
		{"label": _("Active"), "fieldname": "active_users", "fieldtype": "Int", "width": 80},
		{"label": _("Pending Invites"), "fieldname": "pending_invitations", "fieldtype": "Int", "width": 130},
		{"label": _("Used"), "fieldname": "utilisation", "fieldtype": "Percent", "width": 90},
		{"label": _("Signal"), "fieldname": "signal", "fieldtype": "Data", "width": 220},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Tenant",
		filters={"status": ["in", ["Active", "Suspended"]]},
		fields=["name", "tenant_name", "plan_code", "user_quota", "active_users",
		        "pending_invitations"],
		order_by="creation desc",
		limit_page_length=0,
	)
	out = []
	for row in rows:
		quota = cint(row.user_quota) or 1
		used = cint(row.active_users)
		share = used / quota
		if used > quota:
			signal = _("Over quota - enforcement was bypassed somewhere")
		elif share >= 1:
			signal = _("Full - they cannot add anyone")
		elif share >= NEARLY_FULL:
			signal = _("Nearly full - a seat conversation is due")
		elif share <= UNDERUSED:
			signal = _("Barely used - a churn risk worth a call")
		else:
			signal = ""
		out.append({**row, "utilisation": round(share * 100, 1), "signal": signal})
	return sorted(out, key=lambda r: -r["utilisation"])
