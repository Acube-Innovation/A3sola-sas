# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""/register/<key>: the page an event's QR code opens (Solar Event).

Public - a visitor at the stall registers from their phone without an account. The key names
the event; an unknown key or a closed event shows "This registration has closed". The form
posts to api/event_registration.submit.
"""

import frappe

from a3_sola.api import event_registration

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.reg = event_registration.page_context(frappe.form_dict.get("key"))
	context.page_meta_title = context.reg.event_name if context.reg else "Registration closed"
	# A logged-in phone (staff trying the QR) posts with its CSRF token; a guest needs none.
	from frappe.sessions import get_csrf_token

	context.csrf_token = get_csrf_token() if frappe.session.user != "Guest" else ""
	return context
