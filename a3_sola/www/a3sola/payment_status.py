# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The page shown after the checkout window closes.

It waits for the webhook rather than trusting the browser callback, because the callback
is a hint and the webhook is truth. It also gives up gracefully: a customer must never be
left staring at a spinner.
"""

import frappe

from a3_sola.api import signup as signup_api

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Payment status"

	reference = (frappe.form_dict.get("ref") or "").strip()[:40]
	key = (frappe.form_dict.get("t") or "").strip()[:64]
	context.reference = reference
	context.key = key
	context.summary = signup_api.try_signup_summary(reference, key)
	return context
