# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 1 Payment is confirmed on its task's short form, and the fee may be claimed back as
the stamp paper is: the template ticks Allow Reimbursement on it."""

import frappe


def execute():
	frappe.reload_doc("solar_operations", "doctype", "statutory_fee_payment")
	frappe.db.sql("""update `tabInstallation Stage Template Detail` set allow_reimbursement = 1
		where stage_code = 'F1PAY'""")
	for name in frappe.get_all("Installation Stage Template", pluck="name"):
		frappe.clear_document_cache("Installation Stage Template", name)
