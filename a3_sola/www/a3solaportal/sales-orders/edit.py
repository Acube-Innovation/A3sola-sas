# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A sales order is edited on its own page (view): this old address leads there."""

import frappe

from a3_sola.api import sales_order_option

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	frappe.local.flags.redirect_location = sales_order_option.route_of(name) if name else "/a3solaportal/sales-orders"
	raise frappe.Redirect(302)
