# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A panel option's Total Panel Rate is its rate for every panel, and the default panel's is
part of the Total Package Cost - a build-up of the default panel, inverter, batteries, balance
of system and the KSEB, mounting and installation rows that moves no price."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint, flt

from a3_sola.solar_crm.doctype.solar_package.solar_package import package_build_up, price_for, system_cost
from a3_sola.tests.fixtures import make_consumer, package


class TestPackageTotals(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", make_consumer().company))
		self.assertTrue(self.pkg.modules and self.pkg.inverters, "the test package needs a panel and an inverter")
		self.pkg.save()

	def default_panel(self):
		return next((r for r in self.pkg.modules if r.is_default), self.pkg.modules[0])

	def test_a_panel_row_totals_its_rate_for_every_panel(self):
		panel = self.default_panel()
		panel.rate, panel.module_count = 12000, 6
		self.pkg.save()
		self.assertEqual(flt(panel.amount), 72000)

	def test_the_default_panel_is_in_the_total_package_cost_with_the_rest(self):
		panel = self.default_panel()
		panel.rate, panel.module_count = 12000, 6
		self.pkg.save()
		inverter = next((r for r in self.pkg.inverters if r.is_default), self.pkg.inverters[0])
		expected = (72000 + flt(inverter.unit_rate) * (cint(inverter.inverter_count) or 1) + system_cost(self.pkg)
			+ sum(flt(r.amount) for r in self.pkg.kseb_expenses) + sum(flt(r.amount) for r in self.pkg.mounting_expenses)
			+ sum(flt(r.amount) for r in self.pkg.installation_expenses))
		self.assertEqual(flt(self.pkg.total_package_cost, 2), flt(expected, 2))
		self.assertEqual(package_build_up(self.pkg)["panel"], 72000)

	def test_another_default_panel_changes_the_total_and_no_price(self):
		panel = self.default_panel()
		panel.rate, panel.module_count = 12000, 6
		self.pkg.save()
		before, price = flt(self.pkg.total_package_cost), price_for(self.pkg).system_cost
		other = self.pkg.append("modules", {"module_specification": "620 Wp test panel", "module_make": panel.module_make,
			"module_wattage": 620, "module_count": 5, "rate": 15000})
		for row in self.pkg.modules:
			row.is_default = 1 if row is other else 0
		self.pkg.save()
		self.assertEqual(flt(self.pkg.total_package_cost) - before, 75000 - 72000)
		# A build-up only: the package is still priced at its inverter option's Cost.
		self.assertEqual(price_for(self.pkg).system_cost, price)

	def test_the_portal_grid_shows_the_item_with_its_text_and_the_total(self):
		from a3_sola.api import portal_packages

		columns = [c for c in portal_packages._table("modules")["columns"] if c["in_list"]]
		self.assertEqual(columns[0]["fieldname"], "module_item")
		self.assertNotIn("module_specification", [c["fieldname"] for c in columns])
		amount = next(c for c in columns if c["fieldname"] == "amount")
		self.assertTrue(amount["read_only"])
		self.assertEqual(amount["label"], "Total Panel Rate")
