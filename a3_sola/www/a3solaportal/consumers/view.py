# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one consumer: the shared record page, and the consumer's ERPNext Customer
- linked, or converted from here."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("consumers", name) if name else "/a3solaportal/consumers")
	detail_context(context, "consumers", name)
	doc = context.record
	customer = doc.customer if doc.customer and frappe.db.exists("Customer", doc.customer) else None
	context.customer = {
		"name": customer,
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name") if customer else "",
		"desk": "/app/customer/" + frappe.utils.quote(customer) if customer else "",
		"can_convert": not customer and bool(doc.has_permission("write")) and frappe.has_permission("Customer", "create"),
	}
	context.extra_template = "templates/includes/portal_consumer_customer.html"
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
