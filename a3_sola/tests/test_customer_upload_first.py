# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The new customer page starts with the documents that fill it: a tile for each, a way to type
the details in instead, and the form hidden until one or the other. Other create pages keep
their plain Attachments card above a form shown from the start."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

from a3_sola.api.portal_attachments import READERS, offered_types
from a3_sola.www.a3solaportal.collections import get_collection


def page(route):
	set_request(method="GET", path=route)
	response = get_response(route)
	return response.status_code, response.get_data(as_text=True)


class TestCustomerUploadFirst(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_each_tile_is_a_document_the_card_offers_and_can_read(self):
		cfg = get_collection("consumers")
		offered = offered_types(cfg["doctype"])
		for doc_type, icon, fills in cfg["autofill"]:
			self.assertIn((cfg["doctype"], doc_type), READERS, f"{doc_type} has no reader")
			self.assertIn(doc_type, offered, f"{doc_type} is not offered on the customer's card")
			self.assertTrue(icon and fills)

	def test_the_new_customer_page_asks_for_the_documents_first(self):
		code, html = page("a3solaportal/consumers/new")
		self.assertEqual(code, 200)
		self.assertIn("data-autofill", html)
		for doc_type, _icon, _fills in get_collection("consumers")["autofill"]:
			self.assertIn(f'data-autofill-type="{doc_type}"', html)
		self.assertIn("Enter the details manually", html)
		# The form is there to be filled, but hidden until a document is added or typing is chosen.
		self.assertIn("data-autofill-form hidden", html)
		self.assertIn('id="a3s-record-form"', html)

	def test_other_create_pages_keep_the_plain_card(self):
		code, html = page("a3solaportal/site-surveys/new")
		self.assertEqual(code, 200)
		self.assertIn("data-attach", html)
		self.assertNotIn("data-autofill", html)
		self.assertIn('id="a3s-record-form"', html)
