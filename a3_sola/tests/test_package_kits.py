# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Product Bundle or an Item with a BOM chosen on a package's tab is replaced by its items,
each tagged with what it came from and priced at its selling price; on the Inverter and Solar
Panel tabs the rows of one kit are one option (api/package_kits)."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import package_items, package_kits
from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	inverters_for_phase,
	option_rows,
	options,
	package_build_up,
)
from a3_sola.tests.fixtures import default_company, package


def part(code, group="Kit Test Parts", stock=1):
	if not frappe.db.exists("Item Group", group):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": group, "parent_item_group": "All Item Groups",
			"is_group": 0}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": group, "stock_uom": "Nos",
			"is_stock_item": stock, "description": f"{code} as described"}).insert(ignore_permissions=True)
	return code


def bundle(code, items, group="Kit Test Parts"):
	part(code, group, stock=0)
	if not frappe.db.exists("Product Bundle", {"new_item_code": code}):
		frappe.get_doc({"doctype": "Product Bundle", "new_item_code": code,
			"items": [{"item_code": i, "qty": q} for i, q in items]}).insert(ignore_permissions=True)
	return code


def selling_price(item, rate):
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	if not frappe.db.exists("Price List", price_list):
		raise unittest.SkipTest("No selling price list.")
	frappe.get_doc({"doctype": "Item Price", "item_code": item, "price_list": price_list, "price_list_rate": rate}).insert(
		ignore_permissions=True)


class TestPackageKits(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", default_company()))
		self.cable, self.lug = part("Kit Test Cable"), part("Kit Test Lug")
		selling_price(self.cable, 40)

	def tearDown(self):
		frappe.db.rollback()

	def test_a_bundle_on_the_materials_tab_is_replaced_by_its_items(self):
		kit = bundle("Kit Test Cable Set", [(self.cable, 30), (self.lug, 2)])
		inverter = default_inverter(self.pkg).inverter_item
		self.pkg.set("material_bom", [{"item": kit, "qty": 2, "rate": 999, "depends_on": inverter}])
		self.pkg.save()
		rows = self.pkg.material_bom
		self.assertEqual([(r.item, flt(r.qty), flt(r.rate)) for r in rows], [(self.cable, 60, 40), (self.lug, 4, 0)])
		self.assertEqual({(r.bundle_type, r.bundle_ref, flt(r.bundle_qty)) for r in rows}, {("Bundle", kit, 2)})
		self.assertEqual(len({r.bundle_key for r in rows}), 1)
		self.assertEqual([r.description for r in rows], [f"{self.cable} as described", f"{self.lug} as described"])
		self.assertEqual({r.depends_on for r in rows}, {inverter})
		# Saved again, they stay as they are.
		self.pkg.save()
		self.assertEqual(len(self.pkg.material_bom), 2)

	def test_an_inverter_kit_is_one_option_its_parts_counted_in_it(self):
		micro = part("Kit Test Microinverter", group="On-Grid Inverters" if frappe.db.exists("Item Group", "On-Grid Inverters")
			else "Kit Test Parts")
		selling_price(micro, 30000)
		kit = bundle("Kit Test Micro Kit", [(micro, 1), (self.cable, 10)])
		for row in self.pkg.inverters:
			row.is_default = 0
		self.pkg.append("inverters", {"inverter_item": kit, "inverter_specification": "Kit Test micro kit option",
			"inverter_count": 2, "is_default": 1, "inverter_capacity_kw": 3})
		self.pkg.save()
		head = default_inverter(self.pkg)
		parts = [r for r in self.pkg.inverters if r.bundle_part]
		self.assertEqual((head.inverter_item, head.inverter_specification, flt(head.inverter_count), flt(head.unit_rate)),
			(micro, "Kit Test micro kit option", 2, 30000))
		self.assertEqual([(r.inverter_item, flt(r.inverter_count), flt(r.unit_rate), r.is_default) for r in parts],
			[(self.cable, 20, 40, 0)])
		self.assertNotIn(parts[0], options(self.pkg, "inverters"))
		self.assertNotIn(parts[0], inverters_for_phase(self.pkg, None))
		self.assertEqual(option_rows(self.pkg, "inverters", head), [head, parts[0]])
		# The option's amount takes in its parts; the package's BOM, every one of them.
		self.assertEqual(package_build_up(self.pkg)["inverter"], 2 * 30000 + 20 * 40)
		lines = package_items.bom_lines(self.pkg)
		self.assertEqual((lines.get(micro), lines.get(self.cable)), (2, 20))

	def test_the_page_gets_the_rows_a_bundle_opens_into(self):
		kit = bundle("Kit Test Cable Set", [(self.cable, 30), (self.lug, 2)])
		rows = package_kits.expand_row("expenses", frappe.as_json({"item": kit, "qty": 1, "rate": 5}))
		self.assertEqual([(r["item"], r["qty"], r["rate"], r["bundle_type"]) for r in rows],
			[(self.cable, 30, 40, "Bundle"), (self.lug, 2, 0, "Bundle")])
		self.assertEqual(package_kits.expand_row("expenses", frappe.as_json({"item": self.lug, "qty": 1})),
			[{"item": self.lug, "qty": 1}])
