# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Support: our own platform staff find anyone in any company and log in as them to help, and
see the "Log in as" sessions that are open or were held (api/impersonation)."""

import frappe

from a3_sola.api import impersonation
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/support")
	if not impersonation.is_platform_staff():
		frappe.throw("Only our support staff can open this page.", frappe.PermissionError)
	fill_shell(
		context,
		active_route="/a3solaportal/support",
		page_title="Support",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Support"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.boot = {"sessions": impersonation.sessions(limit=50),
		"minutes": impersonation.minutes_for("Platform", 10**6)}
	return context
