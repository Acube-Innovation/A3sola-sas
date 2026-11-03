# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Packages page: an admin's list of the Solar Packages estimates are built from, and the
place to add, duplicate, activate or delete them (api/portal_packages). Admins only."""

import frappe

from a3_sola.api import portal_packages
from a3_sola.api.portal_users import require_admin
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/packages")
	require_admin()
	fill_shell(
		context,
		active_route="/a3solaportal/packages",
		page_title="Packages",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Packages"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.data = portal_packages.packages()
	return context
