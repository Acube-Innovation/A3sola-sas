# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package row's rate fills with its Item's selling price when the Item is chosen."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_packages


class TestPackageItemRate(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.item = frappe.get_doc({"doctype": "Item", "item_code": "_Test Rate Inverter", "item_name": "_Test Rate Inverter",
			"item_group": "All Item Groups", "stock_uom": "Nos", "is_stock_item": 0}).insert()

	def tearDown(self):
		frappe.db.rollback()

	def price(self, rate, uom="Nos"):
		price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
		frappe.get_doc({"doctype": "Item Price", "item_code": self.item.name, "price_list": price_list,
			"price_list_rate": rate, "uom": uom}).insert()

	def test_the_selling_price_is_the_rate(self):
		self.price(16800)
		self.assertEqual(portal_packages.item_rate(self.item.name), 16800)
		self.assertEqual(portal_packages.item_rate(self.item.name, "Nos"), 16800)

	def test_no_price_or_no_item_is_zero(self):
		self.assertEqual(portal_packages.item_rate(self.item.name), 0)
		self.assertEqual(portal_packages.item_rate("_No Such Item"), 0)
		self.assertEqual(portal_packages.item_rate(""), 0)
