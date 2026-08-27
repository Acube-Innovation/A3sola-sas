# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Signup Funnel.

The report that tells marketing which step is leaking. Every signup is counted at the
furthest stage it reached, and the drop-off column is the number that matters: a healthy
funnel loses people at the price, not at the verification email.
"""

import frappe
from frappe import _
from frappe.utils import flt

#: In order. A signup that reached Paid also passed through everything before it.
STAGES = (
	("Submitted", ("Draft", "Awaiting Email Verification", "Verified", "Awaiting Payment",
	               "Payment Failed", "Paid", "Provisioning", "Active", "Abandoned")),
	("Email sent", ("Awaiting Email Verification", "Verified", "Awaiting Payment",
	                "Payment Failed", "Paid", "Provisioning", "Active", "Abandoned")),
	("Verified", ("Verified", "Awaiting Payment", "Payment Failed", "Paid",
	              "Provisioning", "Active")),
	("Reached payment", ("Awaiting Payment", "Payment Failed", "Paid", "Provisioning", "Active")),
	("Paid", ("Paid", "Provisioning", "Active")),
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 180},
		{"label": _("Signups"), "fieldname": "count", "fieldtype": "Int", "width": 110},
		{"label": _("% of Submitted"), "fieldname": "share", "fieldtype": "Percent", "width": 150},
		{"label": _("Dropped Here"), "fieldname": "dropped", "fieldtype": "Int", "width": 130},
		{"label": _("Drop-off %"), "fieldname": "drop_percent", "fieldtype": "Percent", "width": 130},
		{"label": _("Value Reaching Here"), "fieldname": "value", "fieldtype": "Currency", "width": 180},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["creation"] = ["between", [filters.from_date, filters.to_date]]
	if filters.get("plan_code"):
		conditions["plan_code"] = filters.plan_code
	if filters.get("billing_cycle"):
		conditions["billing_cycle"] = filters.billing_cycle

	rows = frappe.get_all(
		"Subscription Signup",
		filters=conditions,
		fields=["status", "total_amount"],
		limit_page_length=0,
	)
	if not rows:
		return []

	out, previous = [], None
	for label, statuses in STAGES:
		reached = [r for r in rows if r.status in statuses]
		count = len(reached)
		value = sum(flt(r.total_amount) for r in reached)
		dropped = (previous - count) if previous is not None else 0
		out.append(
			{
				"stage": label,
				"count": count,
				"share": flt(count * 100.0 / len(rows), 2),
				"dropped": dropped,
				"drop_percent": flt(dropped * 100.0 / previous, 2) if previous else 0.0,
				"value": flt(value, 2),
			}
		)
		previous = count
	return out
