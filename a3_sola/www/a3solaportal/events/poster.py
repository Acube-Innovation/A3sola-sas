# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An event's QR poster: an A4 page to print and stand at the stall (api/events)."""

import frappe

from a3_sola.api import events
from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	name = frappe.form_dict.get("name")
	require_login("/a3solaportal/events/{0}/poster".format(name or ""))
	context.update(events.poster_context(name))
	context.no_cache = 1
	context.no_index = True
	return context
