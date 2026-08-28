# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Settlement Reconciliation Summary.

Fees as a percentage of gross is the trend to watch: it should be flat. A drift means the
mix of payment methods has changed, or the gateway's pricing has, and either is worth
knowing before the year-end.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Settlement"), "fieldname": "name", "fieldtype": "Link", "options": "Settlement Reconciliation", "width": 160},
		{"label": _("Settlement ID"), "fieldname": "settlement_id", "fieldtype": "Data", "width": 180},
		{"label": _("Date"), "fieldname": "settlement_date", "fieldtype": "Date", "width": 110},
		{"label": _("Gross"), "fieldname": "gross_total", "fieldtype": "Currency", "width": 140},
		{"label": _("Fees"), "fieldname": "total_fees", "fieldtype": "Currency", "width": 130},
		{"label": _("Fee %"), "fieldname": "fee_percent", "fieldtype": "Percent", "width": 100},
		{"label": _("Refunds"), "fieldname": "total_refunds", "fieldtype": "Currency", "width": 130},
		{"label": _("Net Settled"), "fieldname": "net_settled", "fieldtype": "Currency", "width": 150},
		{"label": _("Matched"), "fieldname": "matched_count", "fieldtype": "Int", "width": 100},
		{"label": _("Unmatched"), "fieldname": "unmatched_count", "fieldtype": "Int", "width": 120},
		{"label": _("Variance"), "fieldname": "variance_total", "fieldtype": "Currency", "width": 140},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Settlement Reconciliation",
		filters={"docstatus": ["<", 2]},
		fields=[
			"name", "settlement_id", "settlement_date", "gross_total", "total_fees",
			"total_refunds", "net_settled", "matched_count", "unmatched_count",
			"variance_total", "status",
		],
		order_by="settlement_date desc",
		limit_page_length=0,
	)
	for row in rows:
		row["fee_percent"] = (
			flt(flt(row.total_fees) * 100.0 / flt(row.gross_total), 2)
			if flt(row.gross_total) else 0.0
		)
	return rows
