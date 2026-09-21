# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one sales invoice. All logic is shared; this only names the slug."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("sales-invoices", name) if name else "/a3solaportal/sales-invoices")
	detail_context(context, "sales-invoices", name)
	return context
