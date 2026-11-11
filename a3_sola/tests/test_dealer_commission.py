# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's dealer commission (api/dealer_commission), by its own rule: Formula is its base
plus its amount per kW of capacity, Percentage is of the cost before the commission and the
margin, Lump Sum is fixed. A package carrying the commission row has it in each pricing
option's cost, and the row shows the default option's."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import dealer_commission
from a3_sola.solar_crm.doctype.solar_package.solar_package import pricing_build_up
from a3_sola.tests.fixtures import package


class TestDealerCommission(FrappeTestCase):
	def setUp(self):
		if not frappe.db.exists("Item", dealer_commission.ITEM):
			from a3_sola.setup.install import seed_dealer_commission_item

			seed_dealer_commission_item()

	def test_each_rule(self):
		pkg = frappe._dict(capacity_kw=3, dealer_commission_rule="Formula", dealer_commission_base=10000,
			dealer_commission_per_kw=1000)
		self.assertEqual(dealer_commission.amount(pkg, 100000), 13000)
		pkg.update(dealer_commission_rule="Percentage", dealer_commission_percent=5)
		self.assertEqual(dealer_commission.amount(pkg, 125000), 6250)
		pkg.update(dealer_commission_rule="Lump Sum", dealer_commission_lump_sum=7500)
		self.assertEqual(dealer_commission.amount(pkg, 125000), 7500)

	def test_in_the_package_cost(self):
		"""The percentage is of the cost before the commission and the margin; the option's cost
		has both, and the Expenses row shows the default option's commission."""
		doc = frappe.get_doc("Solar Package", package())
		if not doc.get("pricing_options"):
			self.skipTest("The test package has no pricing options.")
		doc.dealer_commission_rule, doc.dealer_commission_percent = "Percentage", 10
		doc.append("expenses", {"item": dealer_commission.ITEM, "qty": 1, "rate": 0})
		doc.price_dealer_commission()
		doc.cost_the_pricing_options()
		default = next((r for r in doc.pricing_options if r.is_default), doc.pricing_options[0])
		parts = pricing_build_up(doc, default)
		before = sum(v for k, v in parts.items() if k not in ("commission", "margin"))
		self.assertAlmostEqual(parts["commission"], flt(before * 0.10, 2), places=2)
		self.assertAlmostEqual(flt(default.cost), flt(sum(parts.values()), 2), places=2)
		row = next(r for r in doc.expenses if dealer_commission.is_commission(r))
		self.assertAlmostEqual(flt(row.rate), parts["commission"], places=2)

	def test_one_row_only(self):
		doc = frappe.get_doc("Solar Package", package())
		for _i in range(2):
			doc.append("expenses", {"item": dealer_commission.ITEM, "qty": 1, "rate": 0})
		with self.assertRaises(frappe.ValidationError):
			doc.price_dealer_commission()
