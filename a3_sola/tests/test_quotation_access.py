# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A quotation made from a proposal reads its items' details and names its customer's
receivable account, as ERPNext checks: so the staff and the dealers who raise it read Item
and pick Account (install_staff_lookups, install_partners) - pick only, the ledgers are not theirs."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.setup import install_partners, install_staff_lookups


def user_with(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"user_type": "System User"}).insert(ignore_permissions=True)
	frappe.get_doc("User", email).add_roles(role)
	return email


class TestQuotationAccess(FrappeTestCase):
	def setUp(self):
		install_staff_lookups.setup()
		install_partners.setup()

	def tearDown(self):
		frappe.set_user("Administrator")

	def check(self, email):
		frappe.set_user(email)
		self.assertTrue(frappe.has_permission("Item", "read"))
		self.assertTrue(frappe.has_permission("Account", "select"))
		# Picked, not read: the chart of accounts stays the accountants'.
		self.assertTrue(frappe.only_has_select_perm("Account"))

	def test_a_sales_coordinator_can_raise_a_quotation(self):
		self.check(user_with("quote.coordinator@a3sola.test", "Solar Sales Coordinator"))

	def test_a_dealer_can_raise_a_quotation(self):
		self.check(user_with("quote.dealer@a3sola.test", "Solar Dealer"))
