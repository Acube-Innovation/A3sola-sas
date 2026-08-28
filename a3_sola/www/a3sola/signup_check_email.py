# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Confirmation that a verification email went out.

Deliberately does not confirm whether the reference is real - it renders the same either
way, because this page is reachable by anyone with a URL.
"""

import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.reference = (frappe.form_dict.get("ref") or "").strip()[:40]
	context.page_meta_title = "Check your email"
	return context
