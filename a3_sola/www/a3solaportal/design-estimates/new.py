# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Step one of a new design estimate: its details, in two columns. Next creates it."""

import frappe

from a3_sola.api import portal_estimate
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/design-estimates/new")
	frappe.has_permission("Solar Design Estimate", "create", throw=True)
	fill_shell(
		context,
		active_route="/a3solaportal/design-estimates",
		page_title="New design estimate",
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Solar Design Estimate", "href": "/a3solaportal/design-estimates"},
			{"label": "New"},
		],
	)
	context.record_name = ""
	context.columns = portal_estimate.detail_columns()
	context.profile = None
	context.cancel_route = "/a3solaportal/design-estimates"
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
