# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Subscription Revenue.

MRR normalised across cycles, because a mix of monthly and annual customers cannot be
compared any other way: an annual subscription is counted as a twelfth per month, not as
a spike in the month it was collected.
"""

import frappe
from frappe import _
from frappe.utils import flt

ACTIVE = ("Active", "Past Due")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 130},
		{"label": _("Cycle"), "fieldname": "billing_cycle", "fieldtype": "Data", "width": 100},
		{"label": _("Subscriptions"), "fieldname": "count", "fieldtype": "Int", "width": 130},
		{"label": _("Active"), "fieldname": "active", "fieldtype": "Int", "width": 90},
		{"label": _("Past Due"), "fieldname": "past_due", "fieldtype": "Int", "width": 100},
		{"label": _("MRR"), "fieldname": "mrr", "fieldtype": "Currency", "width": 140},
		{"label": _("ARR"), "fieldname": "arr", "fieldtype": "Currency", "width": 140},
		{"label": _("Avg per Subscription"), "fieldname": "average", "fieldtype": "Currency", "width": 180},
		{"label": _("Lifetime Collected"), "fieldname": "lifetime", "fieldtype": "Currency", "width": 170},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Platform Subscription",
		filters={"docstatus": 1, "status": ["in", ACTIVE]},
		fields=["plan_code", "billing_cycle", "status", "recurring_amount", "lifetime_value"],
		limit_page_length=0,
	)
	grouped = {}
	for row in rows:
		key = (row.plan_code or "?", row.billing_cycle or "?")
		bucket = grouped.setdefault(
			key,
			{"plan_code": key[0], "billing_cycle": key[1], "count": 0, "active": 0,
			 "past_due": 0, "mrr": 0.0, "lifetime": 0.0},
		)
		bucket["count"] += 1
		bucket["active"] += 1 if row.status == "Active" else 0
		bucket["past_due"] += 1 if row.status == "Past Due" else 0
		# An annual subscription is a twelfth a month, not a spike when it is collected.
		monthly = (
			flt(row.recurring_amount) / 12.0
			if (row.billing_cycle or "").lower() == "annual"
			else flt(row.recurring_amount)
		)
		bucket["mrr"] += monthly
		bucket["lifetime"] += flt(row.lifetime_value)

	out = []
	for bucket in grouped.values():
		bucket["mrr"] = flt(bucket["mrr"], 2)
		bucket["arr"] = flt(bucket["mrr"] * 12, 2)
		bucket["average"] = flt(bucket["mrr"] / bucket["count"], 2) if bucket["count"] else 0.0
		bucket["lifetime"] = flt(bucket["lifetime"], 2)
		out.append(bucket)
	out.sort(key=lambda r: r["mrr"], reverse=True)
	return out
