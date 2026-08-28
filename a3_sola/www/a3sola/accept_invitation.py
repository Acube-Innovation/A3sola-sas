# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Where an invitation link lands. Public, and deliberately incurious.

The page never says whether the token is real - it renders the same form either way and
lets the endpoint decide, with one generic refusal. A page that greeted a valid token
differently would be an invitation-guessing oracle.
"""

import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Accept your invitation"
	context.token = frappe.form_dict.get("token") or ""
	return context
