# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Dunning Effectiveness.

Which step actually recovers money. A sequence where every recovery happens at step one
is a sequence with five steps too many; one where they happen at the final notice is a
sequence that starts too gently.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Step"), "fieldname": "attempt_number", "fieldtype": "Int", "width": 80},
		{"label": _("Action"), "fieldname": "attempt_type", "fieldtype": "Data", "width": 180},
		{"label": _("Attempts"), "fieldname": "attempts", "fieldtype": "Int", "width": 110},
		{"label": _("Recovered"), "fieldname": "recovered", "fieldtype": "Int", "width": 110},
		{"label": _("Recovery %"), "fieldname": "recovery_rate", "fieldtype": "Percent", "width": 130},
		{"label": _("Value Recovered"), "fieldname": "value_recovered", "fieldtype": "Currency", "width": 170},
		{"label": _("Avg Days to Recover"), "fieldname": "avg_days", "fieldtype": "Float", "precision": 1, "width": 180},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Dunning Attempt",
		filters={"parenttype": "Platform Subscription"},
		fields=["parent", "attempt_number", "attempt_type", "outcome", "attempt_date",
		        "payment_order"],
		limit_page_length=0,
	)
	grouped = {}
	for row in rows:
		key = (row.attempt_number or 0, row.attempt_type or "?")
		bucket = grouped.setdefault(
			key,
			{"attempt_number": key[0], "attempt_type": key[1], "attempts": 0,
			 "recovered": 0, "value_recovered": 0.0, "_days": 0.0},
		)
		bucket["attempts"] += 1
		if row.outcome != "Succeeded":
			continue
		bucket["recovered"] += 1
		if row.payment_order:
			order = frappe.db.get_value(
				"Payment Order", row.payment_order,
				["total_amount", "paid_on", "creation"], as_dict=True,
			)
			if order:
				bucket["value_recovered"] += flt(order.total_amount)
				if order.paid_on:
					bucket["_days"] += max(
						date_diff(getdate(order.paid_on), getdate(row.attempt_date)), 0
					)

	out = []
	for bucket in grouped.values():
		recovered = bucket["recovered"]
		bucket["avg_days"] = flt(bucket.pop("_days") / recovered, 1) if recovered else 0.0
		bucket["recovery_rate"] = (
			flt(recovered * 100.0 / bucket["attempts"], 2) if bucket["attempts"] else 0.0
		)
		bucket["value_recovered"] = flt(bucket["value_recovered"], 2)
		out.append(bucket)
	out.sort(key=lambda r: r["attempt_number"])
	return out
