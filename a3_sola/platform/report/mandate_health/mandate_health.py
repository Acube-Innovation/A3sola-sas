# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Mandate Health.

The column that earns this report is "Covers Current Amount". A mandate whose registered
maximum has fallen below the current recurring amount will be declined at the bank on the
next debit, and nothing else surfaces that until the money does not arrive.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Mandate"), "fieldname": "name", "fieldtype": "Link", "options": "Payment Mandate", "width": 160},
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 190},
		{"label": _("Type"), "fieldname": "mandate_type", "fieldtype": "Data", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Recurring Debit"), "fieldname": "recurring_debit_amount", "fieldtype": "Currency", "width": 150},
		{"label": _("Authorised Up To"), "fieldname": "registered_max_amount", "fieldtype": "Currency", "width": 160},
		{"label": _("Covers Current Amount"), "fieldname": "covers", "fieldtype": "Check", "width": 180},
		{"label": _("Needs Auth Each Debit"), "fieldname": "requires_afa_per_debit", "fieldtype": "Check", "width": 180},
		{"label": _("Valid Until"), "fieldname": "valid_until", "fieldtype": "Date", "width": 120},
		{"label": _("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 140},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Payment Mandate",
		filters={"docstatus": ["<", 2]},
		fields=[
			"name", "customer_name", "mandate_type", "status", "recurring_debit_amount",
			"registered_max_amount", "requires_afa_per_debit", "valid_until",
			"platform_subscription",
		],
		limit_page_length=0,
	)
	for row in rows:
		current = flt(
			frappe.db.get_value(
				"Platform Subscription", row.platform_subscription, "recurring_amount"
			)
			or row.recurring_debit_amount
		)
		row["covers"] = 1 if current <= flt(row.registered_max_amount) else 0
		row["days_to_expiry"] = (
			date_diff(getdate(row.valid_until), today()) if row.valid_until else 0
		)
		row.pop("platform_subscription", None)
	# The ones that will fail first, first.
	rows.sort(key=lambda r: (r["covers"], r["status"] != "Active", r["days_to_expiry"]))
	return rows
