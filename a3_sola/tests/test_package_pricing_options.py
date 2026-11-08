# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package is priced by its Pricing Options: each row one of its panels, inverters and
batteries at a package cost. The inverter options' Cost and the Package Cost are worked out
from them, and an estimate is priced at the row for the panel and inverter it is built with."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	inverter_name,
	panel_name,
	price_for,
	pricing_option,
)
from a3_sola.tests.fixtures import make_consumer, package

TEST_PANEL = "620 Wp pricing test panel"


class TestPackagePricingOptions(FrappeTestCase):
	def setUp(self):
		"""The test package with a price list of its own: each inverter on the default panel. The
		test site's packages are unpriced, and a test case's saves outlast its tests, so the panels
		and prices a test adds are taken away again first."""
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", make_consumer().company))
		self.pkg.set("modules", [r for r in self.pkg.modules if r.module_specification != TEST_PANEL])
		self.panel = next((r for r in self.pkg.modules if r.is_default), self.pkg.modules[0])
		self.inverter = next((r for r in self.pkg.inverters if r.is_default), self.pkg.inverters[0])
		self.pkg.set("pricing_options", [])
		for n, row in enumerate(self.pkg.inverters):
			self.pkg.append("pricing_options", {"panel": panel_name(self.panel), "inverter": inverter_name(row),
				"cost": 215000 + 5000 * n, "is_default": 1 if row is self.inverter else 0})
		self.pkg.save()

	def test_every_inverter_is_priced_by_its_row_and_the_package_by_the_default(self):
		self.assertTrue(self.pkg.pricing_options, "the package's prices are its pricing options")
		for row in self.pkg.inverters:
			option = pricing_option(self.pkg, row)
			self.assertEqual(flt(row.cost), flt(option.cost) if option else 0)
		default = next(r for r in self.pkg.pricing_options if r.is_default)
		self.assertEqual(flt(self.pkg.package_cost), flt(default.cost))

	def test_a_new_price_moves_the_inverter_cost_and_the_estimate_price(self):
		option = pricing_option(self.pkg, self.inverter)
		option.cost = 333000
		self.pkg.save()
		self.assertEqual(flt(self.inverter.cost), 333000)
		self.assertEqual(price_for(self.pkg, self.inverter).system_cost, 333000)

	def test_the_same_inverter_on_another_panel_has_a_price_of_its_own(self):
		other = self.pkg.append("modules", {"module_specification": TEST_PANEL, "module_make": self.panel.module_make,
			"module_wattage": 620, "module_count": 5})
		self.pkg.append("pricing_options", {"panel": TEST_PANEL, "inverter": inverter_name(self.inverter), "cost": 250000})
		self.pkg.save()
		self.assertEqual(flt(pricing_option(self.pkg, self.inverter, panel=other).cost), 250000)
		# A panel the package does not price falls back to the inverter's own panel's row.
		own = pricing_option(self.pkg, self.inverter, panel="no such panel")
		self.assertEqual(own.panel, panel_name(self.panel))
		# The inverter's Cost, which the proposal reads, stays its own panel's.
		self.assertEqual(flt(self.inverter.cost), flt(own.cost))

	def test_ticking_another_default_changes_the_package_cost(self):
		self.pkg.append("modules", {"module_specification": TEST_PANEL, "module_make": self.panel.module_make,
			"module_wattage": 620, "module_count": 5})
		other = self.pkg.append("pricing_options", {"panel": TEST_PANEL, "inverter": inverter_name(self.inverter),
			"cost": 260000})
		for row in self.pkg.pricing_options:
			row.is_default = 1 if row is other else 0
		self.pkg.save()
		self.assertEqual(flt(self.pkg.package_cost), 260000)

	def test_a_row_must_name_the_packages_own_parts_and_price_each_build_once(self):
		self.pkg.append("pricing_options", {"panel": "no such panel", "inverter": inverter_name(self.inverter), "cost": 1})
		with self.assertRaises(frappe.ValidationError):
			self.pkg.save()
		self.pkg.reload()
		self.pkg.append("pricing_options", {"panel": panel_name(self.panel), "inverter": inverter_name(self.inverter), "cost": 2})
		with self.assertRaises(frappe.ValidationError):
			self.pkg.save()

	def test_a_package_priced_the_old_way_gets_its_rows(self):
		doc = frappe.copy_doc(self.pkg)
		doc.specification_code = "PRICING-ROWS-TEST"
		doc.item = doc.bom = None
		doc.set("pricing_options", [])
		doc.package_cost = 0
		for row in doc.inverters:
			row.cost = 190000 if row.is_default else 0
		doc.insert()
		self.assertEqual([(r.inverter, flt(r.cost), r.is_default) for r in doc.pricing_options],
			[(inverter_name(next(r for r in doc.inverters if r.is_default)), 190000, 1)])
		self.assertEqual(flt(doc.package_cost), 190000)

	def test_the_portal_shows_the_table_and_no_longer_asks_the_inverter_cost(self):
		from a3_sola.api import portal_packages

		spec = portal_packages._table("pricing_options")
		self.assertEqual([c["fieldname"] for c in spec["columns"]], ["panel", "inverter", "battery", "cost", "is_default"])
		self.assertNotIn("cost", [c["fieldname"] for c in portal_packages._table("inverters")["columns"]])
		tabs = {t["key"]: t for t in portal_packages._layout()}
		self.assertIn("pricing_options", tabs["tab_pricing"]["tables"])
		self.assertTrue(next(f for f in frappe.get_meta("Solar Package").fields if f.fieldname == "package_cost").read_only)
