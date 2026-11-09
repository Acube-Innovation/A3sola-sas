# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's BOM tab as a full BOM (package_bom_tree): the other tabs' rows copied in on save,
each Product Bundle or BOM row followed by its items, and every part counted once."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import package_bom_tree, package_items


class TestPackageBomTree(FrappeTestCase):
	def setUp(self):
		self.package = frappe.db.get_value("Solar Package", {"bom": ["is", "set"]}) or frappe.db.get_value("Solar Package", {})
		if not self.package:
			self.skipTest("No Solar Package on this site.")
		doc = frappe.get_doc("Solar Package", self.package)
		if len(doc.material_bom) < 3 or not doc.kseb_expenses:
			self.skipTest("The package has too few rows to build on.")
		self.doc = doc
		self.parts = [r.item for r in doc.material_bom[:3]]

	def own(self, table):
		return [r for r in self.doc.get(table) if package_bom_tree.is_own(r)]

	def test_the_other_tabs_are_copied_in_and_the_typed_rows_kept(self):
		typed = [(r.item, r.qty) for r in self.own("material_bom")]
		self.doc.save()
		self.assertEqual([(r.item, r.qty) for r in self.own("material_bom")], typed)
		copied = [r for r in self.doc.material_bom if r.source_row]
		inverters = [r for r in self.doc.inverters if r.inverter_item]
		self.assertEqual(len([r for r in copied if r.source_row.startswith("Inverter")]), len(inverters))
		# An inverter option's copy is needed with that inverter only.
		for row in copied:
			if row.source_row.startswith("Inverter"):
				self.assertEqual(row.inverters, row.item)
		self.assertTrue(any(r.source_row.startswith("KSEB") for r in self.doc.expenses))
		# Saved again, the copies are not copied twice.
		count = len(self.doc.material_bom)
		self.doc.save()
		self.assertEqual(len(self.doc.material_bom), count)

	def test_a_bundle_and_a_bom_open_out(self):
		kseb = self.doc.kseb_expenses[0].particulars
		frappe.get_doc({"doctype": "Product Bundle", "new_item_code": kseb,
			"items": [{"item_code": self.parts[1], "qty": 2}, {"item_code": self.parts[2], "qty": 3}]}).insert(ignore_permissions=True)
		bom = frappe.get_doc({"doctype": "BOM", "item": self.parts[0], "company": self.doc.company, "quantity": 1,
			"items": [{"item_code": self.parts[1], "qty": 4}, {"item_code": self.parts[2], "qty": 5}]})
		frappe.flags.mute_messages = True
		try:
			bom.insert(ignore_permissions=True)
			bom.submit()
		finally:
			frappe.flags.mute_messages = False
		self.doc.save()
		rows = list(self.doc.expenses)
		at = next(i for i, r in enumerate(rows) if r.item == kseb and r.row_kind == "Bundle")
		self.assertEqual([(r.item, r.qty, r.row_kind) for r in rows[at + 1:at + 3]],
			[(self.parts[1], 2, "Component"), (self.parts[2], 3, "Component")])
		# Its items are its parts: not counted again in the Expenses total.
		self.assertAlmostEqual(self.doc.total_expenses, sum(r.amount for r in rows if r.row_kind != "Component"), 2)
		rows = list(self.doc.material_bom)
		at = next(i for i, r in enumerate(rows) if r.item == self.parts[0] and package_bom_tree.is_own(r))
		parent = rows[at]
		self.assertEqual((parent.row_kind, parent.bom_no), ("BOM", bom.name))
		self.assertEqual([(r.item, r.qty) for r in rows[at + 1:at + 3]], [(self.parts[1], 4 * parent.qty), (self.parts[2], 5 * parent.qty)])
		# The package's own BOM: the BOM row once, a sub-assembly, not its items on top.
		lines = package_items.bom_lines(self.doc)
		self.assertAlmostEqual(lines[self.parts[0]], parent.qty)
		self.assertEqual(package_bom_tree.line_items(kseb, 2), [(self.parts[1], 4), (self.parts[2], 6)])

	def test_an_estimate_takes_only_the_typed_rows(self):
		from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import package_bom_rows

		typed = len(self.own("material_bom"))
		self.doc.save()
		rows = package_bom_rows(self.doc, None)
		self.assertLessEqual(len(rows["material_bom"]), typed)
		self.assertEqual(rows["bom_expenses"], [{f: r.get(f) for f in ("item", "category", "uom", "qty", "rate", "amount")}
			for r in self.own("expenses") if r.item])
