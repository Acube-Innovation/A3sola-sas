# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The tenant's setup checklist - the things provisioning deliberately did not guess."""

import frappe

from a3_sola.api import onboarding

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in."), frappe.PermissionError)

	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Setting up"
	context.checklist = onboarding.my_checklist()
	return context
