# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Subsidy Receivable Ageing.

Only "Company Funded Gap" claims appear here. Where the customer claims directly the
company has funded nothing, so there is no receivable to age - that absence is deliberate.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

BUCKETS = ((30, "0-30"), (60, "31-60"), (90, "61-90"), (10**6, "90+"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Claim"), "fieldname": "name", "fieldtype": "Link", "options": "Subsidy Claim", "width": 150},
		{"label": _("Installation"), "fieldname": "solar_installation", "fieldtype": "Link", "options": "Solar Installation", "width": 160},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Claim Status"), "fieldname": "claim_status", "fieldtype": "Data", "width": 120},
		{"label": _("Recovery Status"), "fieldname": "recovery_status", "fieldtype": "Data", "width": 140},
		{"label": _("Submitted"), "fieldname": "claim_submitted_on", "fieldtype": "Date", "width": 110},
		{"label": _("Disbursed"), "fieldname": "disbursed_on", "fieldtype": "Date", "width": 110},
		{"label": _("Funded"), "fieldname": "amount_recoverable_from_customer", "fieldtype": "Currency", "width": 130},
		{"label": _("Recovered"), "fieldname": "amount_recovered", "fieldtype": "Currency", "width": 120},
		{"label": _("Written Off"), "fieldname": "written_off", "fieldtype": "Currency", "width": 120},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 130},
		{"label": _("Days"), "fieldname": "age_days", "fieldtype": "Int", "width": 80},
		{"label": _("Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Subsidy Claim",
		filters={
			"company": filters.company,
			"docstatus": 1,
			"claim_model": "Company Funded Gap",
		},
		fields=[
			"name", "solar_installation", "customer", "claim_status", "recovery_status",
			"claim_submitted_on", "disbursed_on", "amount_recoverable_from_customer",
			"amount_recovered", "outstanding_recovery",
		],
		limit_page_length=0,
	)
	written_off = _write_offs({row.name for row in rows})
	out = []
	for row in rows:
		row["written_off"] = flt(written_off.get(row.name), 2)
		row["outstanding"] = flt(
			flt(row.amount_recoverable_from_customer)
			- flt(row.amount_recovered)
			- row["written_off"],
			2,
		)
		if row["outstanding"] <= 0:
			continue
		# Aged from disbursement where we have it: the clock on recovering from the
		# customer starts when the money actually reached them, not when we claimed.
		started = row.disbursed_on or row.claim_submitted_on
		row["age_days"] = date_diff(today(), getdate(started)) if started else 0
		row["bucket"] = next(label for limit, label in BUCKETS if row["age_days"] <= limit)
		out.append(row)
	out.sort(key=lambda r: r["age_days"], reverse=True)
	return out


def _write_offs(claims):
	"""Amounts the client has already given up on, from the posted write-off entries.

	A receivable that has been written off is not outstanding, and leaving it in the
	ageing overstates what is actually recoverable.
	"""
	if not claims:
		return {}
	rows = frappe.get_all(
		"Journal Entry",
		filters={
			"a3s_source_doctype": "Subsidy Claim",
			"a3s_source_document": ["in", list(claims)],
			"a3s_purpose": "Subsidy Write Off",
			"docstatus": 1,
		},
		fields=["a3s_source_document", "total_debit"],
	)
	out = {}
	for row in rows:
		out[row.a3s_source_document] = out.get(row.a3s_source_document, 0.0) + flt(row.total_debit)
	return out
