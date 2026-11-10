# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An inverter option's Inverter Amount is its Rate per Inverter for every inverter, and its Item
Group the group its Item is in - one of the Inverters groups - both set on save."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.solar_crm.doctype.solar_package.solar_package import inverter_groups
from a3_sola.tests.fixtures import default_company, package


class TestPackageInverterRow(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", default_company()))
		self.row = next(r for r in self.pkg.inverters if r.inverter_item)
		self.before = (self.row.unit_rate, self.row.inverter_count, self.row.item_group)

	def tearDown(self):
		pkg = frappe.get_doc("Solar Package", self.pkg.name)
		row = next(r for r in pkg.inverters if r.name == self.row.name)
		row.unit_rate, row.inverter_count = self.before[0], self.before[1]
		pkg.save()

	def test_the_amount_and_group_are_set_on_save(self):
		self.row.unit_rate, self.row.inverter_count, self.row.item_group = 16800, 3, None
		self.pkg.save()
		row = next(r for r in self.pkg.inverters if r.name == self.row.name)
		self.assertEqual(flt(row.amount), 50400)
		group = frappe.db.get_value("Item", row.inverter_item, "item_group")
		self.assertEqual(row.item_group, group if group in inverter_groups() else None)
