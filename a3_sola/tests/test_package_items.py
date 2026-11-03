# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package is made of Items, each row's of its own category (api/package_items)."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import package_items


class TestPackageItems(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_a_row_takes_only_an_item_of_its_category(self):
		panel = frappe.db.get_value("Item", {"item_group": ["in", ["TOPCon Modules", "Bifacial Modules", "Mono PERC Modules"]]})
		inverter = frappe.db.get_value("Item", {"item_group": ["in", ["On-Grid Inverters", "Hybrid Inverters"]]})
		if not (panel and inverter):
			raise unittest.SkipTest("No panel and inverter Items.")
		self.assertTrue(package_items.in_group(panel, "Modules"))
		self.assertFalse(package_items.in_group(inverter, "Modules"))
		doc = frappe.get_doc({"doctype": "Solar Package", "modules": [{"module_item": inverter, "idx": 1}]})
		with self.assertRaises(frappe.ValidationError):
			package_items.validate(doc)
		doc.modules[0].module_item = panel
		package_items.validate(doc)

	def test_each_balance_of_system_type_has_its_group(self):
		self.assertEqual(package_items.system_item_group("Solar Energy Meter"), "Meters")
		self.assertEqual(package_items.system_item_group("Mounting Structure"), "Mounting Structures")
		self.assertEqual(package_items.system_item_group("DCDB"), "Cables and BOS")

	def test_a_component_is_named_with_its_type_where_its_text_does_not_say_it(self):
		row = frappe._dict(system_type="DCDB")
		self.assertEqual(package_items.item_name_for("system_items", row, "With PV fuses at input"), "DCDB - With PV fuses at input")
		row = frappe._dict(system_type="AC Cable")
		self.assertEqual(package_items.item_name_for("system_items", row, "AC cable, 15 m"), "AC cable, 15 m")
		self.assertEqual(package_items.item_name_for("modules", frappe._dict(), "550 Wp Rayzon"), "550 Wp Rayzon")


class TestPackageBOM(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def package(self):
		name = frappe.db.get_value("Solar Package", {"item": ["is", "set"], "bom": ["is", "not set"]})
		if not name:
			raise unittest.SkipTest("No package with an Item and no BOM.")
		doc = frappe.get_doc("Solar Package", name)
		if package_items._missing(doc) or not package_items.bom_lines(doc):
			raise unittest.SkipTest("The package's rows have no Items.")
		return doc

	def test_the_bom_is_the_package_as_quoted(self):
		doc = self.package()
		lines = package_items.bom_lines(doc)
		default = next(r for r in doc.modules if r.is_default)
		self.assertEqual(lines[default.module_item], default.module_count)
		self.assertFalse({r.inverter_item for r in doc.inverters if not r.is_default} - {r.inverter_item for r in doc.inverters if r.is_default} & set(lines))
		made = package_items.create_bom(doc.name)
		bom = frappe.get_doc("BOM", made["bom"])
		self.assertEqual((bom.item, bom.docstatus, bom.is_default), (doc.item, 1, 1))
		self.assertEqual({r.item_code: r.qty for r in bom.items}, lines)

	def test_an_unchanged_package_keeps_its_bom_and_a_changed_one_gets_a_new_one(self):
		doc = self.package()
		first = package_items.create_bom(doc.name)["bom"]
		self.assertTrue(package_items.update_bom(doc.name).get("unchanged"))
		row = next(r for r in doc.modules if r.is_default)
		frappe.db.set_value(row.doctype, row.name, "module_count", (row.module_count or 1) + 1)
		changed = package_items.update_bom(doc.name)
		self.assertEqual(changed["previous"], first)
		self.assertEqual(frappe.db.get_value("BOM", first, ["is_active", "is_default"]), (0, 0))
		self.assertEqual(frappe.db.get_value("Solar Package", doc.name, "bom"), changed["bom"])

	def test_changes_are_said(self):
		self.assertEqual(package_items.changes_between({"A": 1, "B": 2}, {"A": 2, "C": 1}),
			["A: 1.0 → 2.0", "C added (1.0)", "B removed"])
