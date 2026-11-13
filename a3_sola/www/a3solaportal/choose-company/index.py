# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Choose the company to work in, for a login that works in several (api/memberships).

The same list as the top bar's switcher, as a page: for a phone, and the way out when the
company someone was working in is paused."""

import frappe

from a3_sola.api import memberships
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/choose-company")
	fill_shell(
		context,
		active_route="/a3solaportal/choose-company",
		page_title="Choose company",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Choose company"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.choices = memberships.my_companies()
	return context
