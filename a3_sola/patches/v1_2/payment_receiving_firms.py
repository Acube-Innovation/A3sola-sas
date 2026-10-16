# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer's payment is received by one of two firms - Renewcore or RIM Projects - and each
is booked to its own ledger. Every company with an account mapping and no receiving firms yet
gets a ledger per firm under its Bank Accounts ("Renewcore Receipts", "RIM Projects Receipts"),
mapped to the firm; Accounts re-maps a firm to the real bank ledger in the mapping when known.
A company that already lists its firms is left as it is."""

import frappe

FIRMS = ("Renewcore", "RIM Projects")


def execute():
	for doctype in ("payment_receiving_firm", "solar_company_account_mapping"):
		frappe.reload_doc("solar_projects", "doctype", doctype)
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_log")
	for name in frappe.get_all("Solar Company Account Mapping", pluck="name"):
		mapping = frappe.get_doc("Solar Company Account Mapping", name)
		if mapping.get("receiving_firms") or not mapping.company:
			continue
		parent = frappe.db.get_value("Account", {"company": mapping.company, "account_type": "Bank", "is_group": 1}, "name")
		if not parent:
			continue
		for firm in FIRMS:
			mapping.append("receiving_firms", {"firm_name": firm, "account": _ledger(mapping.company, parent, f"{firm} Receipts"),
				"is_active": 1})
		mapping.flags.ignore_permissions = True
		mapping.save()


def _ledger(company, parent, account_name):
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
	if existing:
		return existing
	account = frappe.get_doc({
		"doctype": "Account", "company": company, "account_name": account_name, "parent_account": parent,
		"account_type": "Bank", "is_group": 0,
	})
	account.flags.ignore_permissions = True
	account.insert()
	return account.name
