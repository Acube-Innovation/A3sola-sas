# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package's Materials, Structure and Expenses rows: each taken where the package uses an
Item it depends on (or always), into the package's BOM, and from Excel (api/package_bom_tables)."""

import base64
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.xlsxutils import make_xlsx

from a3_sola.api import package_bom_tables as tables
from a3_sola.api import package_items


def _group():
	group = frappe.db.get_value("Item Group", {"is_group": 0, "name": ["in", ["Cables and BOS", "Solar Consumables"]]}) \
		or frappe.db.get_value("Item Group", {"is_group": 0})
	if not group:
		raise unittest.SkipTest("No leaf Item Group.")
	return group


def _item(code, group=None, uom="Nos"):
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": group or _group(),
			"stock_uom": uom, "is_stock_item": 1}).insert(ignore_permissions=True)
	return code


def _sheet(rows, name="material.xlsx"):
	content = make_xlsx(rows, "Sheet").getvalue()
	return "data:application/octet-stream;base64," + base64.b64encode(content).decode(), name


class TestMaterialBOM(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def package(self):
		string, micro = _item("_Test MB String, 3 kW"), _item("_Test MB Micro 1 kW")
		pipe, lug = _item("_Test MB GI Pipe"), _item("_Test MB Lug")
		return frappe.get_doc({"doctype": "Solar Package", "inverters": [
			{"inverter_item": string, "is_default": 1, "idx": 1}, {"inverter_item": micro, "idx": 2}],
			"material_bom": [
				{"item": pipe, "qty": 4, "rate": 250, "idx": 1},
				{"item": lug, "qty": 10, "rate": 5, "depends_on": micro, "idx": 2}]})

	def test_a_row_takes_its_amount_its_description_and_only_the_packages_items(self):
		doc = self.package()
		tables.validate(doc)
		self.assertEqual([r.amount for r in doc.material_bom], [1000, 50])
		self.assertEqual(doc.material_bom[0].uom, "Nos")
		self.assertEqual(doc.material_bom[0].description, tables.item_text("_Test MB GI Pipe"))
		doc.material_bom[1].depends_on = "_Test MB Unknown Inverter"
		with self.assertRaises(frappe.ValidationError):
			tables.validate(doc)

	def test_the_bom_takes_the_rows_of_what_the_package_uses(self):
		doc = self.package()
		self.assertEqual(tables.bom_lines(doc), {"_Test MB GI Pipe": 4})
		doc.inverters[0].is_default, doc.inverters[1].is_default = 0, 1
		self.assertEqual(tables.bom_lines(doc), {"_Test MB GI Pipe": 4, "_Test MB Lug": 10})
		self.assertEqual(package_items.bom_lines(doc), {"_Test MB Micro 1 kW": 1, "_Test MB GI Pipe": 4, "_Test MB Lug": 10})

	def test_a_row_may_depend_on_any_of_the_packages_items(self):
		doc = self.package()
		panel, other_panel = _item("_Test MB Panel 550"), _item("_Test MB Panel 620")
		doc.set("modules", [{"module_item": panel, "is_default": 1}, {"module_item": other_panel}])
		doc.material_bom[1].depends_on = f"{other_panel}\n_Test MB Micro 1 kW"
		self.assertEqual(tables.own_items(doc)[:2], ["_Test MB Panel 550", "_Test MB Panel 620"])
		self.assertNotIn("_Test MB Lug", tables.bom_lines(doc))
		doc.modules[0].is_default, doc.modules[1].is_default = 0, 1
		self.assertIn("_Test MB Lug", tables.bom_lines(doc))

	def test_a_row_in_another_uom_goes_in_by_its_conversion(self):
		doc = self.package()
		if not frappe.db.exists("UOM", "Box"):
			raise unittest.SkipTest("No UOM Box.")
		item = frappe.get_doc("Item", "_Test MB Lug")
		item.append("uoms", {"uom": "Box", "conversion_factor": 50})
		item.save(ignore_permissions=True)
		doc.material_bom[1].update({"uom": "Box", "qty": 2, "depends_on": ""})
		self.assertEqual(tables.bom_lines(doc)["_Test MB Lug"], 100)

	def test_items_are_read_by_code_or_name_and_may_hold_commas(self):
		keys = tables._item_keys([_item("_Test MB String, 3 kW"), _item("_Test MB Micro 1 kW")])
		self.assertEqual(tables._match("_Test MB String, 3 kW, _test mb micro 1 kw", keys),
			(["_Test MB String, 3 kW", "_Test MB Micro 1 kW"], None))
		self.assertEqual(tables._match("All", keys), ([], None))
		self.assertEqual(tables._match("_Test MB Micro 1 kW; Enphase", keys), ([], "Enphase"))

	def test_a_sheet_finds_its_items_and_makes_the_missing_ones(self):
		group, pipe = _group(), _item("_Test MB GI Pipe")
		inverter = _item("_Test MB Micro 1 kW")
		content, name = _sheet([tables.columns(),
			[pipe, "", "", "", 4, 250, None, ""],
			["_Test MB New Clamp", "Galvanised clamp", group, "Nos", "6", None, 120, inverter],
			[None, None, None, None, None, None, None, None]])
		read = tables.read_sheet(content, name, "material_bom", [inverter])
		self.assertEqual(read["created"], ["_Test MB New Clamp"])
		self.assertEqual([(r["item"], r["qty"], r["rate"], r["description"], r["depends_on"]) for r in read["rows"]],
			[(pipe, 4, 250, "", ""), ("_Test MB New Clamp", 6, 20, "Galvanised clamp", inverter)])
		self.assertEqual(frappe.db.get_value("Item", "_Test MB New Clamp", "item_group"), group)

	def test_an_older_sheet_reads_its_inverters_as_depends_on(self):
		rail, inverter = _item("_Test SB Rail"), _item("_Test MB Micro 1 kW")
		content, name = _sheet([["Item Name", "Qty", "Rate", "Depends on Inverter", "Depends on Roof Type", "Panal Capacity"],
			[rail, 2, 900, inverter, "RCC Flat", "3 kW"], [rail, 1, 900, "", "", ""]])
		read = tables.read_sheet(content, name, "structure_boms", [inverter])
		self.assertEqual([r["depends_on"] for r in read["rows"]], [inverter, ""])
		content, name = _sheet([["Item Name", "Depends On"], [rail, "_Test Not On The Package"]])
		with self.assertRaises(frappe.ValidationError):
			tables.read_sheet(content, name, "expenses", [inverter])

	def test_a_sheet_with_mistakes_makes_nothing_and_says_every_one(self):
		content, name = _sheet([tables.columns(),
			["_Test MB Made Too Early", "", _group(), "", 1, 1, None, ""],
			["_Test MB No Category", "", "", "", 1, 1, None, ""],
			["_Test MB GI Pipe", "", "", "", "four", 1, None, ""]])
		_item("_Test MB GI Pipe")
		with self.assertRaises(frappe.ValidationError) as raised:
			tables.read_sheet(content, name, "material_bom", [])
		self.assertIn("Row 3", str(raised.exception))
		self.assertIn("Row 4", str(raised.exception))
		self.assertFalse(frappe.db.exists("Item", "_Test MB Made Too Early"))
