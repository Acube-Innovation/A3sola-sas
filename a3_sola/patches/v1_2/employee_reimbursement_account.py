# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An "Employee Reimbursement" account under each company's Current Liabilities: a supplier's
bill an employee paid from their own pocket is paid from it (api/supplier_bill), so ERPNext
shows the supplier paid and the company owing the employee until the claim is paid back. Cash
type, as ERPNext pays only from a Bank or Cash account."""

import frappe

ACCOUNT = "Employee Reimbursement"


def execute():
	for company, abbr in frappe.get_all("Company", fields=["name", "abbr"], as_list=True):
		if frappe.db.exists("Account", {"company": company, "account_name": ACCOUNT}):
			continue
		parent = frappe.db.get_value("Account", {"company": company, "account_name": "Current Liabilities", "is_group": 1}, "name")
		if not parent:
			continue
		frappe.get_doc({"doctype": "Account", "account_name": ACCOUNT, "company": company, "parent_account": parent,
			"account_type": "Cash", "root_type": "Liability", "report_type": "Balance Sheet", "is_group": 0,
			"account_currency": frappe.db.get_value("Company", company, "default_currency")}).insert(ignore_permissions=True)
