# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Set a password from the link a new user is sent (api/portal_users): the portal's own page,
so the user lands in the portal - Frappe's /update-password would send staff to the desk.

The password itself goes to Frappe's update_password with the link's key: its policy, its
one-time key and its sign-in stay as they are."""

import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Set your password"
	context.key = (frappe.form_dict.get("key") or "").strip()
	# The browser may already be signed in (an admin opening the link he sent): its session
	# then checks the CSRF token, and a post without it is refused as "Invalid Request".
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
