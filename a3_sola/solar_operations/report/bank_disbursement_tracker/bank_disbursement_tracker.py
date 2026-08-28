# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Bank Disbursement Tracker.

Chasing is done branch by branch, so the report is grouped that way."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Loan"), "fieldname": "name", "fieldtype": "Link", "options": "Loan Application", "width": 150},
		{"label": _("Lender"), "fieldname": "lender", "fieldtype": "Data", "width": 140},
		{"label": _("Branch"), "fieldname": "lender_branch", "fieldtype": "Data", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
		{"label": _("Sanctioned"), "fieldname": "sanctioned_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Disbursed"), "fieldname": "total_disbursed", "fieldtype": "Currency", "width": 130},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 130},
		{"label": _("Advance On"), "fieldname": "advance_received_on", "fieldtype": "Date", "width": 110},
		{"label": _("Days Since Advance"), "fieldname": "days_since_advance", "fieldtype": "Int", "width": 150},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Loan Application",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "lender", "lender_branch", "solar_consumer", "status",
			"sanctioned_amount", "total_disbursed", "outstanding", "advance_received_on",
		],
		order_by="lender, lender_branch",
		limit_page_length=0,
	)
	for row in rows:
		row["days_since_advance"] = (
			date_diff(today(), getdate(row.advance_received_on)) if row.advance_received_on else 0
		)
	return rows
