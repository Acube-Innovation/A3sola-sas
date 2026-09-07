# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The create-a-lead form.

Login required. The form posts to `a3_sola.api.leads.create_lead`; this page only
renders the fields and hands the browser a CSRF token, because the write itself belongs
in one guarded endpoint rather than being reconstructed here.
"""

import frappe

from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/leads/new")
	fill_shell(
		context,
		active_route="/a3solaportal/leads",
		page_title="New lead",
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Leads", "href": "/a3solaportal/leads"},
			{"label": "New"},
		],
	)

	# The POST to the create endpoint is an unsafe method on an authenticated session, so
	# it needs a CSRF token. Generated here and read back from a meta tag by the form JS.
	context.csrf_token = frappe.sessions.get_csrf_token()

	context.status_options = [
		"Lead", "Open", "Replied", "Opportunity", "Quotation",
		"Lost Quotation", "Interested", "Converted", "Do Not Contact",
	]
	# Existing Lead Sources for the optional dropdown; empty is fine.
	context.sources = frappe.get_all("Lead Source", pluck="name", order_by="name")
	return context
