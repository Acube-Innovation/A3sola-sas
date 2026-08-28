# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Unreconciled Payments.

Both directions, because they mean different things. A captured payment with no
settlement line usually means the gateway has not paid out yet - or has a problem. A
settlement line with no payment means money moved that this system never recorded, which
is an integration bug and the more serious of the two.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

from a3_sola.api import reconciliation


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Direction"), "fieldname": "direction", "fieldtype": "Data", "width": 240},
		{"label": _("Reference"), "fieldname": "reference", "fieldtype": "Data", "width": 200},
		{"label": _("Gateway Payment ID"), "fieldname": "gateway_payment_id", "fieldtype": "Data", "width": 200},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 140},
		{"label": _("Age (days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 120},
		{"label": _("What It Means"), "fieldname": "meaning", "fieldtype": "Data", "width": 320},
	]


def get_data(filters):
	result = reconciliation.unreconciled_payments(filters.get("older_than_days"))
	out = []

	for row in result["payments_without_settlement"]:
		out.append(
			{
				"direction": _("Captured, not yet settled"),
				"reference": row.get("payment_order"),
				"gateway_payment_id": row.get("gateway_payment_id"),
				"amount": flt(row.get("amount")),
				"age_days": date_diff(today(), getdate(row.get("creation"))),
				"meaning": _("We took the money but the gateway has not paid it out."),
			}
		)

	for row in result["settlement_lines_without_payment"]:
		out.append(
			{
				"direction": _("Settled, no matching payment"),
				"reference": row.get("parent"),
				"gateway_payment_id": row.get("gateway_payment_id"),
				"amount": flt(row.get("gross_amount")),
				"age_days": (
					date_diff(today(), getdate(row.get("settled_on")))
					if row.get("settled_on") else 0
				),
				"meaning": _("Money moved that this system has no record of. Investigate."),
			}
		)

	out.sort(key=lambda r: r["age_days"], reverse=True)
	return out
