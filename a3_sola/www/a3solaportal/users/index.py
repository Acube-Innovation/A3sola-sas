# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Users page: an admin's list of everyone who uses the system - admins, employees,
contractors and dealers - and the place to add, change, disable or delete them, reset their
passwords and send their welcome (api/portal_users). Admins only."""

import frappe

from a3_sola.api import portal_users
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/users")
	portal_users.require_admin()
	fill_shell(
		context,
		active_route="/a3solaportal/users",
		page_title="Users",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Users"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.data = portal_users.users()
	context.choices = portal_users.options()
	return context
