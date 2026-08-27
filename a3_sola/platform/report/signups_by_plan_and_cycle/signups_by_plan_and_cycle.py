# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Signups by Plan and Cycle.

Volume and snapshot value. The average per signup is the number to watch: a month of
Starter-monthly signups and a month of Growth-annual signups look the same on a count.
"""

import frappe
from frappe import _
from frappe.utils import flt

PAID = ("Paid", "Provisioning", "Active")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 130},
		{"label": _("Cycle"), "fieldname": "billing_cycle", "fieldtype": "Data", "width": 100},
		{"label": _("Signups"), "fieldname": "signups", "fieldtype": "Int", "width": 100},
		{"label": _("Verified"), "fieldname": "verified", "fieldtype": "Int", "width": 100},
		{"label": _("Paid"), "fieldname": "paid", "fieldtype": "Int", "width": 90},
		{"label": _("Avg Additional Users"), "fieldname": "avg_additional_users", "fieldtype": "Float", "precision": 1, "width": 170},
		{"label": _("Snapshot Value"), "fieldname": "value", "fieldtype": "Currency", "width": 150},
		{"label": _("Avg per Signup"), "fieldname": "average", "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["creation"] = ["between", [filters.from_date, filters.to_date]]

	rows = frappe.get_all(
		"Subscription Signup",
		filters=conditions,
		fields=["plan_code", "billing_cycle", "status", "total_amount", "additional_users",
		        "is_email_verified"],
		limit_page_length=0,
	)
	grouped = {}
	for row in rows:
		key = (row.plan_code or "?", row.billing_cycle or "?")
		bucket = grouped.setdefault(
			key,
			{"plan_code": key[0], "billing_cycle": key[1], "signups": 0, "verified": 0,
			 "paid": 0, "value": 0.0, "_users": 0},
		)
		bucket["signups"] += 1
		bucket["verified"] += 1 if row.is_email_verified else 0
		bucket["paid"] += 1 if row.status in PAID else 0
		bucket["value"] += flt(row.total_amount)
		bucket["_users"] += int(row.additional_users or 0)

	out = []
	for bucket in grouped.values():
		count = bucket["signups"]
		bucket["avg_additional_users"] = flt(bucket.pop("_users") / count, 1)
		bucket["average"] = flt(bucket["value"] / count, 2)
		bucket["value"] = flt(bucket["value"], 2)
		out.append(bucket)
	out.sort(key=lambda r: r["value"], reverse=True)
	return out
