# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Statutory Recovery Register.

Money the company fronted to the DISCOM on the customer's behalf, and what has come back.
None of this is contract value and none of it is margin - the client's own proposals say
these are reimbursed against receipts - so it is tracked entirely on its own.
"""

import frappe
from frappe import _
from frappe.utils import flt
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Recovery"), "fieldname": "name", "fieldtype": "Link", "options": "Statutory Fee Recovery", "width": 150},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Paid by Company"), "fieldname": "fees_paid_by_company", "fieldtype": "Currency", "width": 150},
		{"label": _("Reimbursed"), "fieldname": "reimbursed_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Outstanding"), "fieldname": "outstanding_reimbursement", "fieldtype": "Currency", "width": 140},
		{"label": _("Refund Expected"), "fieldname": "refund_expected", "fieldtype": "Currency", "width": 150},
		{"label": _("Refund Received"), "fieldname": "refund_received", "fieldtype": "Currency", "width": 150},
		{"label": _("Refund Written Off"), "fieldname": "refund_written_off", "fieldtype": "Currency", "width": 160},
		{"label": _("Refund Outstanding"), "fieldname": "refund_outstanding", "fieldtype": "Currency", "width": 160},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Statutory Fee Recovery",
		filters={"company": filters.company, "docstatus": ["<", 2]},
		fields=[
			"name", "project", "customer", "fees_paid_by_company", "reimbursed_amount",
			"outstanding_reimbursement", "refund_expected", "refund_received",
			"refund_written_off", "status",
		],
		limit_page_length=0,
	)
	for row in rows:
		# What the DISCOM still owes back, after anything the client has given up on.
		row["refund_outstanding"] = flt(
			flt(row.refund_expected) - flt(row.refund_received) - flt(row.refund_written_off), 2
		)
	rows.sort(key=lambda r: flt(r["outstanding_reimbursement"]), reverse=True)
	return rows
