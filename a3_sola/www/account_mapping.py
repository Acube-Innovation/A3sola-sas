# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The one settings screen a tenant admin may use: their own ledger accounts.

A3 Sola Settings itself is site-wide and unreachable by any customer role - one tenant
editing it would change behaviour for every other tenant on the instance. The account
mapping is the exception, because it is genuinely per-company and it is the first item on
every new tenant's setup checklist. See api/tenant_settings.py for how the scoping is
enforced; nothing here is trusted.
"""

import frappe

from a3_sola.api import tenant_settings

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in."), frappe.PermissionError)

	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Account mapping"
	try:
		context.mapping = tenant_settings.get_account_mapping()
		context.accounts = tenant_settings.my_accounts()
	except frappe.PermissionError:
		context.mapping = None
		context.accounts = []
	return context
