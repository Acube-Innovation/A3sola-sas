# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package's Material BOM and Structure BOMs: their rows by inverter, roof type and
capacity, into the package's BOM, and from Excel (api/package_bom_tables)."""

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


def _roofs():
	roofs = frappe.get_all("Roof Type", fields=["name", "roof_type", "company"], order_by="name asc", limit=2)
	if len(roofs) < 2:
		raise unittest.SkipTest("Needs two roof types.")
	return roofs


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
				{"item": lug, "qty": 10, "rate": 5, "inverters": micro, "idx": 2}]})

	def test_a_row_takes_its_amount_and_only_the_packages_inverters(self):
		doc = self.package()
		tables.validate(doc)
		self.assertEqual([r.amount for r in doc.material_bom], [1000, 50])
		self.assertEqual(doc.material_bom[0].uom, "Nos")
		doc.material_bom[1].inverters = "_Test MB Unknown Inverter"
		with self.assertRaises(frappe.ValidationError):
			tables.validate(doc)

	def test_the_bom_takes_the_rows_of_the_default_inverter(self):
		doc = self.package()
		self.assertEqual(tables.bom_lines(doc), {"_Test MB GI Pipe": 4})
		doc.inverters[0].is_default, doc.inverters[1].is_default = 0, 1
		self.assertEqual(tables.bom_lines(doc), {"_Test MB GI Pipe": 4, "_Test MB Lug": 10})
		self.assertEqual(package_items.bom_lines(doc), {"_Test MB Micro 1 kW": 1, "_Test MB GI Pipe": 4, "_Test MB Lug": 10})

	def test_a_row_in_another_uom_goes_in_by_its_conversion(self):
		doc = self.package()
		if not frappe.db.exists("UOM", "Box"):
			raise unittest.SkipTest("No UOM Box.")
		item = frappe.get_doc("Item", "_Test MB Lug")
		item.append("uoms", {"uom": "Box", "conversion_factor": 50})
		item.save(ignore_permissions=True)
		doc.material_bom[1].update({"uom": "Box", "qty": 2, "inverters": ""})
		self.assertEqual(tables.bom_lines(doc)["_Test MB Lug"], 100)

	def test_inverters_are_read_by_code_name_or_specification_and_may_hold_commas(self):
		keys = tables._inverter_keys([{"inverter_item": _item("_Test MB String, 3 kW"), "inverter_specification": "Solinteg 3 kW"},
			{"inverter_item": _item("_Test MB Micro 1 kW")}])
		self.assertEqual(tables._match("_Test MB String, 3 kW, _test mb micro 1 kw", keys),
			(["_Test MB String, 3 kW", "_Test MB Micro 1 kW"], None))
		self.assertEqual(tables._match("Solinteg 3 kW", keys), (["_Test MB String, 3 kW"], None))
		self.assertEqual(tables._match("All", keys), ([], None))
		self.assertEqual(tables._match("Solinteg 3 kW; Enphase", keys), ([], "Enphase"))

	def test_a_sheet_finds_its_items_and_makes_the_missing_ones(self):
		group, pipe = _group(), _item("_Test MB GI Pipe")
		inverter = _item("_Test MB Micro 1 kW")
		content, name = _sheet([tables.columns("material_bom"),
			[pipe, "", "", 4, 250, None, ""],
			["_Test MB New Clamp", group, "Nos", "6", None, 120, inverter],
			[None, None, None, None, None, None, None]])
		read = tables.read_sheet(content, name, "material_bom", [{"inverter_item": inverter}])
		self.assertEqual(read["created"], ["_Test MB New Clamp"])
		self.assertEqual([(r["item"], r["qty"], r["rate"], r["inverters"]) for r in read["rows"]],
			[(pipe, 4, 250, ""), ("_Test MB New Clamp", 6, 20, inverter)])
		self.assertEqual(frappe.db.get_value("Item", "_Test MB New Clamp", "item_group"), group)

	def test_a_sheet_with_mistakes_makes_nothing_and_says_every_one(self):
		content, name = _sheet([tables.columns("material_bom"),
			["_Test MB Made Too Early", _group(), "", 1, 1, None, ""],
			["_Test MB No Category", "", "", 1, 1, None, ""],
			["_Test MB GI Pipe", "", "", "four", 1, None, ""]])
		_item("_Test MB GI Pipe")
		with self.assertRaises(frappe.ValidationError) as raised:
			tables.read_sheet(content, name, "material_bom", [])
		self.assertIn("Row 3", str(raised.exception))
		self.assertIn("Row 4", str(raised.exception))
		self.assertFalse(frappe.db.exists("Item", "_Test MB Made Too Early"))


class TestStructureBOMs(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def package(self):
		flat, sheet = (r.name for r in _roofs())
		rail, clamp, bolt = _item("_Test SB Rail"), _item("_Test SB Clamp"), _item("_Test SB Bolt")
		return frappe.get_doc({"doctype": "Solar Package", "roof_type": flat, "capacity_kw": 3, "structure_boms": [
			{"item": rail, "qty": 2, "rate": 900, "idx": 1},
			{"item": clamp, "qty": 12, "rate": 30, "roof_types": f"{flat}, {sheet}", "panel_capacities": "3.0, 5", "idx": 2},
			{"item": bolt, "qty": 20, "rate": 4, "roof_types": sheet, "idx": 3}]})

	def test_a_row_keeps_real_roof_types_and_capacities(self):
		doc = self.package()
		tables.validate(doc)
		self.assertEqual(doc.structure_boms[1].panel_capacities, "3, 5")
		self.assertEqual(doc.structure_boms[1].amount, 360)
		doc.structure_boms[2].panel_capacities = "three"
		with self.assertRaises(frappe.ValidationError):
			tables.validate(doc)
		doc.structure_boms[2].update({"panel_capacities": "", "roof_types": "_Test No Such Roof"})
		with self.assertRaises(frappe.ValidationError):
			tables.validate(doc)

	def test_the_bom_takes_the_rows_of_the_packages_roof_type_and_capacity(self):
		doc = self.package()
		self.assertEqual(tables.bom_lines(doc), {"_Test SB Rail": 2, "_Test SB Clamp": 12})
		doc.capacity_kw = 4.4
		self.assertEqual(tables.bom_lines(doc), {"_Test SB Rail": 2})
		doc.roof_type = _roofs()[1].name
		self.assertEqual(tables.bom_lines(doc), {"_Test SB Rail": 2, "_Test SB Bolt": 20})

	def test_capacities_are_read_as_kw(self):
		self.assertEqual(tables._capacities(["5 kW", "3", "4.40", "3.0kw"]), (["3", "4.4", "5"], None))
		self.assertEqual(tables._capacities(["3", "big"]), ([], "big"))
		self.assertEqual(tables._capacities(tables._pieces("All")), ([], None))

	def test_a_sheet_names_roof_types_as_they_read(self):
		roofs = _roofs()
		rail = _item("_Test SB Rail")
		content, name = _sheet([["Item Name", "Qty", "Rate", "Depends on Roof Type", "Panal Capacity"],
			[rail, 2, 900, f"{roofs[0].roof_type}, {roofs[1].name}", "3 kW; 5"],
			[rail, 1, 900, "", ""]])
		read = tables.read_sheet(content, name, "structure_boms")
		self.assertEqual([(r["roof_types"], r["panel_capacities"]) for r in read["rows"]],
			[(f"{roofs[0].name}, {roofs[1].name}", "3, 5"), ("", "")])
		content, name = _sheet([["Item Name", "Depends on Roof Type"], [rail, "_Test No Such Roof"]])
		with self.assertRaises(frappe.ValidationError):
			tables.read_sheet(content, name, "structure_boms")
