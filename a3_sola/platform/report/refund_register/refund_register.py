# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Refund Register.

Refunds as a percentage of collections is the number to watch. A rising rate against one
reason - provisioning failed, service not delivered - is a product problem wearing a
finance costume.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Refund"), "fieldname": "name", "fieldtype": "Link", "options": "Payment Refund", "width": 160},
		{"label": _("Type"), "fieldname": "refund_type", "fieldtype": "Data", "width": 150},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 190},
		{"label": _("Amount"), "fieldname": "refund_amount", "fieldtype": "Currency", "width": 140},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Approved By"), "fieldname": "approved_by", "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Age (days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 110},
		{"label": _("Order"), "fieldname": "payment_order", "fieldtype": "Link", "options": "Payment Order", "width": 160},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Payment Refund",
		filters={"docstatus": ["<", 2]},
		fields=["name", "refund_type", "reason", "refund_amount", "status", "approved_by",
		        "creation", "payment_order"],
		order_by="creation desc",
		limit_page_length=0,
	)
	for row in rows:
		row["age_days"] = date_diff(today(), getdate(row.creation))
	if not rows:
		return []

	collected = flt(
		frappe.db.get_value("Payment Order", {"status": "Paid"}, "sum(total_amount)")
	)
	refunded = flt(sum(flt(r["refund_amount"]) for r in rows if r["status"] == "Processed"))
	rows.append(
		{
			"name": None,
			"refund_type": _("TOTAL"),
			"reason": _("{0}% of {1} collected").format(
				round(refunded * 100.0 / collected, 2) if collected else 0,
				frappe.utils.fmt_money(collected, currency="INR"),
			),
			"refund_amount": refunded,
		}
	)
	return rows
