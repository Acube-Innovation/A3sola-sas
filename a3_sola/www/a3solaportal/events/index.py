# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Events: exhibitions and campaigns where visitors register by QR code (Solar Event,
api/events). The list, and the form to add or change an event. Staff only."""

import frappe

from a3_sola.api import events
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/events")
	events.require_staff()
	fill_shell(context, active_route="/a3solaportal/events", page_title="Events",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Events"}])
	context.events = events.event_rows()
	context.can_create = bool(frappe.has_permission("Solar Event", "create"))
	context.main_wide = True
	return context
