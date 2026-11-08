# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A new sales order: one submitted quotation of a lead, ordered (api/sales_order_option)."""

from a3_sola.api import sales_order_option
from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/sales-orders/new")
	sales_order_option.page_context(context)
	return context
