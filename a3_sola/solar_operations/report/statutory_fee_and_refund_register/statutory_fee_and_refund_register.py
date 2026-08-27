# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Statutory Fee & Refund Register.

Fees the company fronted, what has been reimbursed, and the 80% refund - money the client
currently cannot see at all."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Payment"), "fieldname": "name", "fieldtype": "Link", "options": "Statutory Fee Payment", "width": 150},
		{"label": _("Installation"), "fieldname": "solar_installation", "fieldtype": "Link", "options": "Solar Installation", "width": 150},
		{"label": _("Fee Type"), "fieldname": "fee_type", "fieldtype": "Data", "width": 130},
		{"label": _("Paid By"), "fieldname": "paid_by", "fieldtype": "Data", "width": 190},
		{"label": _("Paid"), "fieldname": "amount_gross", "fieldtype": "Currency", "width": 110},
		{"label": _("Receipt"), "fieldname": "has_receipt", "fieldtype": "Check", "width": 80},
		{"label": _("Reimbursable"), "fieldname": "reimbursable_from_customer", "fieldtype": "Currency", "width": 130},
		{"label": _("Reimbursed"), "fieldname": "reimbursed_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Refundable"), "fieldname": "refundable_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Refund Status"), "fieldname": "refund_status", "fieldtype": "Data", "width": 130},
		{"label": _("Refund Received"), "fieldname": "refund_received_amount", "fieldtype": "Currency", "width": 140},
		{"label": _("Days Since Claim"), "fieldname": "days_since_claim", "fieldtype": "Int", "width": 130},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Statutory Fee Payment",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "solar_installation", "fee_type", "paid_by", "amount_gross", "receipt",
			"reimbursable_from_customer", "reimbursed_amount", "refundable_amount",
			"refund_status", "refund_received_amount", "refund_claimed_on",
		],
		limit_page_length=0,
	)
	for row in rows:
		row["has_receipt"] = 1 if row.receipt else 0
		row["days_since_claim"] = (
			date_diff(today(), getdate(row.refund_claimed_on)) if row.refund_claimed_on else 0
		)
	return rows
