# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Invoice and Tax Register.

Shaped for GSTR-1: one row per invoice with the split, the place of supply and the
customer GSTIN. The GSTIN capture rate at the foot is the number worth watching - an
invoice without one cannot give the customer input credit, and they will ask.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Subscription Invoice", "width": 200},
		{"label": _("Date"), "fieldname": "invoice_date", "fieldtype": "Date", "width": 110},
		{"label": _("Customer"), "fieldname": "customer_legal_name", "fieldtype": "Data", "width": 200},
		{"label": _("GSTIN"), "fieldname": "customer_gstin", "fieldtype": "Data", "width": 160},
		{"label": _("Place of Supply"), "fieldname": "place_of_supply", "fieldtype": "Data", "width": 150},
		{"label": _("Taxable Value"), "fieldname": "taxable_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Rate %"), "fieldname": "tax_rate", "fieldtype": "Float", "precision": 2, "width": 90},
		{"label": _("Type"), "fieldname": "tax_type", "fieldtype": "Data", "width": 110},
		{"label": _("IGST"), "fieldname": "igst_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("CGST"), "fieldname": "cgst_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("SGST"), "fieldname": "sgst_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 140},
		{"label": _("Status"), "fieldname": "payment_status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["invoice_date"] = ["between", [filters.from_date, filters.to_date]]

	rows = frappe.get_all(
		"Subscription Invoice",
		filters=conditions,
		fields=[
			"name", "invoice_date", "customer_legal_name", "customer_gstin",
			"place_of_supply", "taxable_value", "tax_rate", "tax_type", "igst_amount",
			"cgst_amount", "sgst_amount", "grand_total", "payment_status",
		],
		order_by="invoice_date, name",
		limit_page_length=0,
	)
	if not rows:
		return []

	with_gstin = len([r for r in rows if r.customer_gstin])
	rows.append(
		{
			"name": None,
			"customer_legal_name": _("{0} invoices - GSTIN captured on {1} ({2}%)").format(
				len(rows), with_gstin, round(with_gstin * 100.0 / len(rows), 1)
			),
			"taxable_value": flt(sum(flt(r["taxable_value"]) for r in rows), 2),
			"igst_amount": flt(sum(flt(r["igst_amount"]) for r in rows), 2),
			"cgst_amount": flt(sum(flt(r["cgst_amount"]) for r in rows), 2),
			"sgst_amount": flt(sum(flt(r["sgst_amount"]) for r in rows), 2),
			"grand_total": flt(sum(flt(r["grand_total"]) for r in rows), 2),
		}
	)
	return rows
