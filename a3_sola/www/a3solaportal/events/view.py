# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One event: its QR code and links, the funnel, and everyone who registered - with their
proposal one tap away on WhatsApp (api/events). Staff only."""

import frappe

from a3_sola.api import events
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	name = frappe.form_dict.get("name")
	require_login("/a3solaportal/events/" + (name or ""))
	ctx = events.view_context(name)
	fill_shell(context, active_route="/a3solaportal/events", page_title=ctx.doc.event_name,
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Events", "href": "/a3solaportal/events"},
			{"label": ctx.doc.event_name}])
	context.update(ctx)
	context.main_wide = True
	return context
