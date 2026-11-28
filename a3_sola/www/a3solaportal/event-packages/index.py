# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Event Packages page: an admin sets, for the company, which package an event visitor gets
by their electricity bill and answers (api/event_package_rules). Admins only."""

import frappe

from a3_sola.api import event_package_rules, portal_users
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login(event_package_rules.ROUTE)
	portal_users.require_admin()
	fill_shell(
		context,
		active_route=event_package_rules.ROUTE,
		page_title="Event Packages",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Event Packages"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.rules_data = event_package_rules.page_data(frappe.form_dict.get("company"))
	return context
