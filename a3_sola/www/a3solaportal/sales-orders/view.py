# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One sales order: its quotation's order details, bill of materials and terms. A draft can
change its dates or be pointed at another quotation, and be submitted; a submitted one is
read here and amended from ERPNext (api/sales_order_option)."""

import frappe

from a3_sola.api import sales_order_option
from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(sales_order_option.route_of(name) if name else "/a3solaportal/sales-orders")
	sales_order_option.page_context(context, name)
	return context
