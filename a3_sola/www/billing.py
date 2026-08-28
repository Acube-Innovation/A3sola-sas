# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The subscribed customer's billing page. Login required, ownership from the session."""

import frappe

from a3_sola.api import billing_portal

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in to see your billing."), frappe.PermissionError)

	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Billing"
	context.subscriptions = billing_portal.my_subscriptions()
	context.invoices = billing_portal.my_invoices()
	return context
