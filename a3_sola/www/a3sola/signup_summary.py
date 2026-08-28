# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The post-verification order summary.

Reads only through `get_signup_summary`, which returns the handful of fields this page
needs and nothing internal. The key in the URL proves the caller is the applicant.
"""

import frappe

from a3_sola.api import signup

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Your order"

	reference = (frappe.form_dict.get("ref") or "").strip()[:40]
	key = (frappe.form_dict.get("t") or "").strip()[:64]
	context.reference = reference
	context.key = key

	context.summary = signup.try_signup_summary(reference, key)
	return context
