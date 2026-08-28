# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Collection Performance.

Split by collection route, because that split is the whole design decision: if assisted
renewal collects as reliably as auto-debit, the friction was not worth it, and if it
collects better, the RBI ceiling is doing the client a favour.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Data", "width": 170},
		{"label": _("Cycle"), "fieldname": "billing_cycle", "fieldtype": "Data", "width": 100},
		{"label": _("Cycles Due"), "fieldname": "due", "fieldtype": "Int", "width": 120},
		{"label": _("Collected"), "fieldname": "collected", "fieldtype": "Int", "width": 110},
		{"label": _("Failed"), "fieldname": "failed", "fieldtype": "Int", "width": 100},
		{"label": _("Success %"), "fieldname": "success_rate", "fieldtype": "Percent", "width": 120},
		{"label": _("Value Due"), "fieldname": "value_due", "fieldtype": "Currency", "width": 150},
		{"label": _("Value Collected"), "fieldname": "value_collected", "fieldtype": "Currency", "width": 160},
	]


def get_data(filters):
	subscriptions = {
		row.name: row
		for row in frappe.get_all(
			"Platform Subscription",
			filters={"docstatus": 1},
			fields=["name", "collection_route", "billing_cycle"],
			limit_page_length=0,
		)
	}
	if not subscriptions:
		return []

	cycles = frappe.get_all(
		"Subscription Billing Cycle",
		filters={"parent": ["in", list(subscriptions)], "parenttype": "Platform Subscription"},
		fields=["parent", "outcome", "amount"],
		limit_page_length=0,
	)
	grouped = {}
	for cycle in cycles:
		subscription = subscriptions.get(cycle.parent)
		if not subscription:
			continue
		key = (subscription.collection_route or "?", subscription.billing_cycle or "?")
		bucket = grouped.setdefault(
			key,
			{"route": key[0], "billing_cycle": key[1], "due": 0, "collected": 0,
			 "failed": 0, "value_due": 0.0, "value_collected": 0.0},
		)
		if cycle.outcome in ("Pending", "Skipped"):
			continue
		bucket["due"] += 1
		bucket["value_due"] += flt(cycle.amount)
		if cycle.outcome == "Collected":
			bucket["collected"] += 1
			bucket["value_collected"] += flt(cycle.amount)
		elif cycle.outcome == "Failed":
			bucket["failed"] += 1

	out = []
	for bucket in grouped.values():
		bucket["success_rate"] = (
			flt(bucket["collected"] * 100.0 / bucket["due"], 2) if bucket["due"] else 0.0
		)
		bucket["value_due"] = flt(bucket["value_due"], 2)
		bucket["value_collected"] = flt(bucket["value_collected"], 2)
		out.append(bucket)
	out.sort(key=lambda r: r["value_due"], reverse=True)
	return out
