# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Page Layout page: an admin picks a page and ticks which of its fields, sections or
parts are shown (api/page_layout). Hidden from the portal only - the desk is unchanged.
Admins only."""

import frappe

from a3_sola.api import page_layout, portal_users
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login(page_layout.ROUTE)
	portal_users.require_admin()
	fill_shell(
		context,
		active_route=page_layout.ROUTE,
		page_title="Page Layout",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Page Layout"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.pages = page_layout.pages()
	keys = [p["key"] for p in context.pages]
	asked = frappe.form_dict.get("page")
	context.current = page_layout.page(asked if asked in keys else keys[0])
	return context
