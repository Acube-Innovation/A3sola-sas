# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Consume a verification token from the emailed link."""

import frappe

from a3_sola.api import signup

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Verify your email"

	token = (frappe.form_dict.get("token") or "").strip()
	if not token:
		context.state = "missing"
		return context

	try:
		result = signup.verify_email(token)
		context.state = "verified"
		context.next_url = result["next"]
	except frappe.TooManyRequestsError:
		context.state = "throttled"
	except Exception:
		# Every failure - expired, reused, wrong, never existed - lands here, because
		# telling them apart would let somebody enumerate valid tokens.
		context.state = "invalid"
	return context
