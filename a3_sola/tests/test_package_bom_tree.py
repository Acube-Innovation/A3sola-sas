# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's Materials, Structure and Expenses tabs hold only the rows typed or uploaded into
them: a save copies nothing in from the other tabs, and the rows an earlier save added that way
are taken out. A bundle chosen there is replaced by its items (api/package_kits), which go into
the package's own ERPNext BOM."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import package_bom_tables, package_bom_tree
from a3_sola.tests.fixtures import default_company, package

TABLES = ("material_bom", "structure_boms", "expenses")


def part(code):
	"""An Item to build with, in a group of its own."""
	if not frappe.db.exists("Item Group", "BOM Test Parts"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "BOM Test Parts",
			"parent_item_group": "All Item Groups", "is_group": 0}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "BOM Test Parts",
			"stock_uom": "Nos", "is_stock_item": 0}).insert(ignore_permissions=True)
	return code


class TestPackageBomTab(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", default_company()))

	def tearDown(self):
		frappe.set_user("Administrator")
		pkg = frappe.get_doc("Solar Package", self.pkg.name)
		for table in TABLES:
			pkg.set(table, [])
		pkg.save()
		for name in frappe.get_all("Product Bundle", filters={"new_item_code": "BOM Tree Test Kit"}, pluck="name"):
			frappe.delete_doc("Product Bundle", name, force=True, ignore_permissions=True)

	def items(self, table):
		return [r.item for r in self.pkg.get(table)]

	def test_a_save_copies_nothing_in_from_the_other_tabs(self):
		# The package has rows on its other tabs that a save once copied into the BOM tab.
		self.assertTrue(self.pkg.inverters and (self.pkg.kseb_expenses or self.pkg.installation_expenses))
		self.pkg.set("material_bom", [{"item": part("BOM Tree Test Lug"), "qty": 10, "rate": 5}])
		self.pkg.set("expenses", [{"item": part("BOM Tree Test Labour"), "qty": 1, "rate": 7500}])
		self.pkg.save()
		self.pkg.save()
		self.assertEqual(self.items("material_bom"), ["BOM Tree Test Lug"])
		self.assertEqual(self.items("expenses"), ["BOM Tree Test Labour"])
		self.assertFalse(any(r.get(f) for t in TABLES for r in self.pkg.get(t) for f in package_bom_tree.TREE_FIELDS))
		self.assertEqual(flt(self.pkg.total_expenses), 7500)

	def test_rows_an_earlier_save_added_are_taken_out(self):
		lug, labour = part("BOM Tree Test Lug"), part("BOM Tree Test Labour")
		self.pkg.set("material_bom", [
			{"item": lug, "qty": 10, "rate": 5, "row_kind": "Bundle"},
			{"item": labour, "qty": 2, "rate": 1, "row_kind": "Component"},
			{"item": labour, "qty": 1, "rate": 300, "source_row": "Inverter row 1"},
		])
		self.pkg.set("expenses", [
			{"item": labour, "qty": 1, "rate": 1180, "source_row": "KSEB row 1"},
			{"item": labour, "qty": 1, "rate": 7500},
		])
		self.pkg.save()
		self.assertEqual([(r.item, r.row_kind) for r in self.pkg.material_bom], [(lug, None)])
		self.assertEqual([flt(r.amount) for r in self.pkg.expenses], [7500])
		self.assertEqual(flt(self.pkg.total_expenses), 7500)

	def test_a_bundle_is_replaced_by_its_items_which_go_into_the_package_bom(self):
		kit, cable, clamp = part("BOM Tree Test Kit"), part("BOM Tree Test Cable"), part("BOM Tree Test Clamp")
		frappe.get_doc({"doctype": "Product Bundle", "new_item_code": kit,
			"items": [{"item_code": cable, "qty": 2}, {"item_code": clamp, "qty": 3}]}).insert(ignore_permissions=True)
		self.pkg.set("material_bom", [{"item": kit, "qty": 2, "rate": 900}])
		self.pkg.save()
		# Its items, each saying which bundle it came from (api/package_kits).
		self.assertEqual(self.items("material_bom"), [cable, clamp])
		self.assertEqual({(r.bundle_type, r.bundle_ref) for r in self.pkg.material_bom}, {("Bundle", kit)})
		lines = package_bom_tables.bom_lines(self.pkg)
		self.assertEqual((lines.get(cable), lines.get(clamp)), (4, 6))
		self.assertNotIn(kit, lines)
