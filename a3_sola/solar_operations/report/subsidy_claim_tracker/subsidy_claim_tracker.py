# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Subsidy Claim Tracker.

PCR ageing, disbursement variance and - for company-funded jobs - the outstanding recovery
that is real working capital."""

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
		{"label": _("Claim"), "fieldname": "name", "fieldtype": "Link", "options": "Subsidy Claim", "width": 150},
		{"label": _("Installation"), "fieldname": "solar_installation", "fieldtype": "Link", "options": "Solar Installation", "width": 150},
		{"label": _("Model"), "fieldname": "claim_model", "fieldtype": "Data", "width": 170},
		{"label": _("Status"), "fieldname": "claim_status", "fieldtype": "Data", "width": 140},
		{"label": _("PCR On"), "fieldname": "pcr_uploaded_on", "fieldtype": "Date", "width": 100},
		{"label": _("Days Pending"), "fieldname": "days_since_pcr", "fieldtype": "Int", "width": 110},
		{"label": _("Expected"), "fieldname": "expected_subsidy_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Disbursed"), "fieldname": "disbursed_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Variance"), "fieldname": "variance_amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Outstanding Recovery"), "fieldname": "outstanding_recovery", "fieldtype": "Currency", "width": 170},
		{"label": _("Ageing"), "fieldname": "bucket", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Subsidy Claim",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "solar_installation", "claim_model", "claim_status", "pcr_uploaded_on",
			"days_since_pcr", "expected_subsidy_amount", "disbursed_amount",
			"variance_amount", "outstanding_recovery",
		],
		limit_page_length=0,
	)
	for row in rows:
		days = row.days_since_pcr or 0
		row["bucket"] = (
			"0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
		)
	return rows
