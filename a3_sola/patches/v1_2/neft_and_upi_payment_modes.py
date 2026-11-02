# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""NEFT/RTGS and UPI as Modes of Payment - how suppliers' bills are mostly paid, offered first on
the Supplier Invoice task's payment (api/supplier_bill.PAYMENT_MODES_FIRST)."""

import frappe

MODES = ("NEFT/RTGS", "UPI")


def execute():
	for mode in MODES:
		if not frappe.db.exists("Mode of Payment", mode):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": mode, "type": "Bank", "enabled": 1}).insert(
				ignore_permissions=True)
