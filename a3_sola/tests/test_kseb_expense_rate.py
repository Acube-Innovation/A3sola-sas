# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's KSEB expense rows read as Rate x Quantity: a fee row is its fee once, a row added by
hand is priced at its Rate times its Quantity, and a row with only an Amount keeps it."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.tests.fixtures import default_company, package


class TestKsebExpenseRate(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", default_company()))
		self.item = frappe.db.get_value("Item", {"item_group": "KSEB Expenses", "disabled": 0})
		if not self.item:
			self.skipTest("No KSEB Expenses Item.")

	def tearDown(self):
		pkg = frappe.get_doc("Solar Package", self.pkg.name)
		pkg.set("kseb_expenses", [r for r in pkg.kseb_expenses if r.source])
		pkg.save()

	def test_fee_rows_read_as_their_fee_once(self):
		self.pkg.save()
		for row in self.pkg.kseb_expenses:
			if row.source:
				self.assertEqual((flt(row.rate), flt(row.qty)), (flt(row.amount), 1), row.particulars)

	def test_a_row_added_by_hand_is_rate_times_quantity(self):
		self.pkg.append("kseb_expenses", {"particulars": self.item, "rate": 750, "qty": 2})
		self.pkg.append("kseb_expenses", {"particulars": self.item, "rate": 400})
		self.pkg.append("kseb_expenses", {"particulars": self.item, "amount": 999})
		self.pkg.save()
		hand = [r for r in self.pkg.kseb_expenses if not r.source]
		self.assertEqual([flt(r.amount) for r in hand], [1500, 400, 999])


class TestInstallationExpenseRate(FrappeTestCase):
	"""The installation line is the roof type's rate per kW for the panel kW where the roof type has
	one, else its typed Rate x Quantity; rows added by hand are their own Rate x Quantity."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", default_company()))
		self.roof = self.pkg.roof_type

	def tearDown(self):
		pkg = frappe.get_doc("Solar Package", self.pkg.name)
		pkg.roof_type = self.roof
		pkg.set("installation_expenses", [r for r in pkg.installation_expenses if r.source == "installation"])
		pkg.save()

	def test_the_line_follows_the_roof_type_and_hand_rows_their_rate(self):
		item = self.pkg.installation_expenses[0].item
		self.pkg.append("installation_expenses", {"item": item, "rate": 400, "qty": 2})
		self.pkg.save()
		line, hand = self.pkg.installation_expenses[0], self.pkg.installation_expenses[-1]
		self.assertEqual(line.source, "installation")
		rate = flt(frappe.db.get_value("Roof Type", self.pkg.roof_type, "installation_rate_per_kw")) if self.pkg.roof_type else 0
		if rate:
			self.assertEqual(flt(line.rate), rate)
			self.assertAlmostEqual(flt(line.amount), rate * flt(line.qty), 2)
		self.assertEqual(flt(hand.amount), 800)

	def test_without_a_roof_rate_the_line_is_priced_as_typed(self):
		self.pkg.roof_type = None
		line = self.pkg.installation_expenses[0]
		line.rate, line.qty = 2500, 3
		self.pkg.save()
		self.assertEqual(flt(self.pkg.installation_expenses[0].amount), 7500)
