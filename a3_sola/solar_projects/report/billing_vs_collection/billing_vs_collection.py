# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Billing vs Collection.

Unbilled balance and outstanding are two different problems - one is ours to raise, the
other is the customer's to pay - so they never share a column.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Billing Plan"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Billing Plan", "width": 150},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Contract Value"), "fieldname": "gross_contract_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Triggered"), "fieldname": "total_triggered", "fieldtype": "Currency", "width": 120},
		{"label": _("Invoiced"), "fieldname": "total_invoiced", "fieldtype": "Currency", "width": 120},
		{"label": _("Collected"), "fieldname": "total_collected", "fieldtype": "Currency", "width": 120},
		{"label": _("Outstanding"), "fieldname": "total_outstanding", "fieldtype": "Currency", "width": 120},
		{"label": _("Unbilled"), "fieldname": "unbilled_balance", "fieldtype": "Currency", "width": 120},
		{"label": _("Billing %"), "fieldname": "billing_completion_percent", "fieldtype": "Percent", "width": 110},
		{"label": _("Triggered Not Invoiced"), "fieldname": "triggered_not_invoiced", "fieldtype": "Currency", "width": 180},
		{"label": _("Oldest Unpaid (days)"), "fieldname": "oldest_unpaid_days", "fieldtype": "Int", "width": 160},
		{"label": _("DSO (days)"), "fieldname": "dso_days", "fieldtype": "Int", "width": 110},
		{"label": _("Statutory Outstanding"), "fieldname": "statutory_outstanding", "fieldtype": "Currency", "width": 170},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Solar Billing Plan",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "project", "customer", "gross_contract_value", "total_triggered",
			"total_invoiced", "total_collected", "total_outstanding", "unbilled_balance",
			"billing_completion_percent", "statutory_outstanding",
		],
		limit_page_length=0,
	)
	ageing = _customer_ageing(filters.company)
	for row in rows:
		# Work the company has earned but not yet asked to be paid for.
		row["triggered_not_invoiced"] = flt(flt(row.total_triggered) - flt(row.total_invoiced), 2)
		measures = ageing.get(row.customer, {})
		row["oldest_unpaid_days"] = measures.get("oldest_unpaid_days", 0)
		row["dso_days"] = measures.get("dso_days", 0)
	rows.sort(key=lambda r: flt(r["triggered_not_invoiced"]), reverse=True)
	return rows


def _customer_ageing(company):
	"""Days sales outstanding, per customer, across everything they owe.

	DSO belongs to the customer rather than to one job: a customer who is slow on a job
	the client finished last year is the same collection problem on the one starting now.
	"""
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"company": company, "docstatus": 1},
		fields=["customer", "posting_date", "grand_total", "outstanding_amount"],
		limit_page_length=0,
	)
	measures = {}
	for invoice in invoices:
		row = measures.setdefault(
			invoice.customer, {"billed": 0.0, "outstanding": 0.0, "oldest_unpaid_days": 0}
		)
		row["billed"] += flt(invoice.grand_total)
		if flt(invoice.outstanding_amount) > 0:
			row["outstanding"] += flt(invoice.outstanding_amount)
			row["oldest_unpaid_days"] = max(
				row["oldest_unpaid_days"], date_diff(today(), getdate(invoice.posting_date))
			)

	for row in measures.values():
		# Outstanding measured against the average day's billing over the last year.
		daily = row["billed"] / 365.0
		row["dso_days"] = int(row["outstanding"] / daily) if daily else 0
	return measures
