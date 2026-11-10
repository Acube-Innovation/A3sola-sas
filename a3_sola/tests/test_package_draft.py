# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package is saved as a Draft without its Pricing Options, to finish later; it needs one to be
made Active (Solar Package.require_pricing_options)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.tests.test_package_options import make_package


class TestPackageDraft(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def unpriced(self, status):
		doc = make_package(save=False, status=status)
		doc.set("pricing_options", [])
		doc.package_cost = 0
		for row in doc.inverters:
			row.cost = 0
		return doc

	def test_a_draft_saves_without_pricing_options(self):
		doc = self.unpriced("Draft")
		doc.insert(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("Solar Package", doc.name))
		self.assertFalse(doc.pricing_options)

	def test_an_active_package_needs_one(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self.unpriced("Active").insert(ignore_permissions=True)
		self.assertIn("Active", str(raised.exception))

	def test_a_draft_is_asked_for_one_when_made_active(self):
		doc = self.unpriced("Draft")
		doc.insert(ignore_permissions=True)
		doc.status = "Active"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
