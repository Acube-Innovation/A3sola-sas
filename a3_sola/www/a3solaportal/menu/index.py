# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Menu page: an admin ticks which items of the portal's left menu are shown
(api/portal_menu). Hidden from the menu only - the pages still open by link. Admins only."""

import frappe

from a3_sola.api import portal_menu, portal_users
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login(portal_menu.ROUTE)
	portal_users.require_admin()
	fill_shell(
		context,
		active_route=portal_menu.ROUTE,
		page_title="Menu",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Menu"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.groups = portal_menu.menu()
	return context
