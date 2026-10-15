# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Loan Documents (LOAN) is bank work, as the seed scopes it: on a template that has it as the
company's, it moves to Bank Activity, and so do the jobs' LOAN tasks - the project board shows
it in the Bank column, which a financed job alone has.

Only rows still on Company Activity move; any other scope was chosen and stays.
"""

import frappe


def execute():
	for doctype in ("Installation Stage Template Detail", "Installation Stage Log"):
		frappe.db.sql(
			f"""update `tab{doctype}` set activity_scope = 'Bank Activity'
			where stage_code = 'LOAN' and activity_scope = 'Company Activity'"""
		)
	frappe.clear_cache(doctype="Installation Stage Template")
