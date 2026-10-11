# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One quotation: its option's details, bill of materials and terms, and its PDF. A draft
can be pointed at another option and submitted; a submitted one is read here and amended
from ERPNext. The route `/a3solaportal/quotations/<name>` is mapped here by a website
route rule in the platform registry."""

import frappe

from a3_sola.api import cost_estimate, quotation_option
from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(cost_estimate.route_of(name) if name else "/a3solaportal/quotations")
	quotation_option.page_context(context, name)
	return context
