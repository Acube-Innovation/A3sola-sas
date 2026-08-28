# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The checkout page.

Renders the order from the pricing snapshot and opens the gateway's own hosted checkout.
No card field is ever posted to a Frappe endpoint - the card never touches this server,
which is what keeps the whole application out of PCI scope.
"""

import frappe

from a3_sola.api import signup as signup_api

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Checkout"

	reference = (frappe.form_dict.get("ref") or "").strip()[:40]
	key = (frappe.form_dict.get("t") or "").strip()[:64]
	context.reference = reference
	context.key = key
	context.summary = signup_api.try_signup_summary(reference, key)

	if not context.summary:
		return context

	order = frappe.db.get_value(
		"Payment Order",
		{"subscription_signup": reference},
		[
			"name", "status", "total_amount", "subtotal", "tax_amount", "currency",
			"tax_type", "igst_amount", "cgst_amount", "sgst_amount",
			"collection_mode", "collection_reason", "gateway_order_id",
		],
		as_dict=True,
		order_by="creation desc",
	)
	from a3_sola.api.gateways.razorpay_client import mock_mode

	context.order = order
	context.already_paid = bool(order and order.status == "Paid")
	# Mock mode replaces the gateway's hosted checkout with a simulated panel. It is
	# stated on the page in plain words: nobody should be able to mistake a simulated
	# payment for a real one.
	context.mock_mode = mock_mode()
	# The renewal route is stated up front rather than discovered in a year's time.
	context.renewal_note = (order or {}).get("collection_reason")
	return context
