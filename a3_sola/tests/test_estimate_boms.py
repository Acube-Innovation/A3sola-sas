# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A design estimate's Material BOM, Structure BOM and Expenses: copied from its package for
the inverter it is built on and its roof, changed on the estimate, and shown - never kept -
beside the proposal, the quotation and the sales order."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import bom_tables
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey, name_of, package


def part(code):
	"""An Item to build with, in a group of its own."""
	if not frappe.db.exists("Item Group", "BOM Test Parts"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "BOM Test Parts",
			"parent_item_group": "All Item Groups", "is_group": 0}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "BOM Test Parts",
			"stock_uom": "Nos", "is_stock_item": 0}).insert(ignore_permissions=True)
	return code


class TestEstimateBoms(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		company = self.consumer.company
		self.flat = name_of("Roof Type", "roof_type", "RCC Flat", company)
		self.metal = name_of("Roof Type", "roof_type", "Metal Sheet", company)
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", company))
		self.default = next(r for r in self.pkg.inverters if r.is_default)
		self.other = next(r for r in self.pkg.inverters if not r.is_default)
		self.pkg.set("material_bom", [
			{"item": part("BOM Test Lug"), "qty": 10, "rate": 5},
			{"item": part("BOM Test DCDB"), "qty": 1, "rate": 2000, "inverters": self.default.inverter_item},
			{"item": part("BOM Test Optimiser"), "qty": 6, "rate": 900, "inverters": self.other.inverter_item},
		])
		self.pkg.set("structure_boms", [
			{"item": part("BOM Test Flat Leg"), "qty": 8, "rate": 300, "roof_types": self.flat, "panel_capacities": "3"},
			{"item": part("BOM Test Sheet Clamp"), "qty": 12, "rate": 40, "roof_types": self.metal},
		])
		self.pkg.set("expenses", [{"item": part("BOM Test Labour"), "qty": 1, "rate": 7500}])
		self.pkg.save()
		self.survey = make_survey(self.consumer, roof_type=self.flat)

	def tearDown(self):
		frappe.set_user("Administrator")
		pkg = frappe.get_doc("Solar Package", self.pkg.name)
		for table in ("material_bom", "structure_boms", "expenses"):
			pkg.set(table, [])
		pkg.save()

	def estimate(self, **kwargs):
		return make_estimate(self.consumer, self.survey, with_default_options=False, solar_package=self.pkg.name, **kwargs)

	def items(self, doc, table):
		return [r.item for r in doc.get(table)]

	def test_a_new_estimate_takes_the_rows_for_its_inverter_and_roof(self):
		est = self.estimate()
		self.assertEqual(self.items(est, "material_bom"), ["BOM Test Lug", "BOM Test DCDB"])
		self.assertEqual(self.items(est, "structure_bom"), ["BOM Test Flat Leg"])
		self.assertEqual(self.items(est, "bom_expenses"), ["BOM Test Labour"])
		dcdb = est.material_bom[1]
		self.assertEqual((dcdb.category, dcdb.uom, flt(dcdb.amount)), ("BOM Test Parts", "Nos", 2000))
		self.assertTrue(est.bom_basis)

	def test_rows_changed_on_the_estimate_stay_until_the_roof_changes(self):
		est = self.estimate()
		est.material_bom[0].qty = 25
		est.save()
		est.reload()
		self.assertEqual((flt(est.material_bom[0].qty), flt(est.material_bom[0].amount)), (25, 125))
		est.roof_type = self.metal
		est.save()
		self.assertEqual(self.items(est, "structure_bom"), ["BOM Test Sheet Clamp"])
		self.assertEqual(flt(est.material_bom[0].qty), 10, "copied again for the new roof")

	def test_the_estimates_price_is_not_built_from_them(self):
		est = self.estimate()
		total = flt(est.commercials()["total"])
		est.bom_expenses[0].rate = 99999
		est.save()
		self.assertEqual(flt(est.commercials()["total"]), total)

	def test_a_package_given_rows_later_still_reaches_the_estimate(self):
		for table in ("material_bom", "structure_boms", "expenses"):
			self.pkg.set(table, [])
		self.pkg.save()
		est = self.estimate()
		self.assertFalse(est.material_bom or est.bom_basis)
		self.pkg.append("expenses", {"item": part("BOM Test Labour"), "qty": 1, "rate": 7500})
		self.pkg.save()
		est.save()
		self.assertEqual(self.items(est, "bom_expenses"), ["BOM Test Labour"])

	def test_an_estimate_from_before_shows_its_packages_rows(self):
		est = self.estimate()
		for table in ("material_bom", "structure_bom", "bom_expenses"):
			frappe.db.delete("Design Estimate BOM Item", {"parent": est.name, "parentfield": table})
		frappe.db.set_value("Solar Design Estimate", est.name, "bom_basis", None)
		shown = {t["key"]: [r["item"] for r in t["rows"]] for t in bom_tables(est.name)}
		self.assertEqual(shown["material_bom"], ["BOM Test Lug", "BOM Test DCDB"])
		self.assertEqual(shown["bom_expenses"], ["BOM Test Labour"])

	def test_step_two_has_the_tabs_and_saves_a_change(self):
		from a3_sola.api import portal_estimate

		est = self.estimate()
		state = portal_estimate.tab_state(est.name)["state"]
		sections = {s["key"]: s for s in state["sections"]}
		self.assertEqual([s["key"] for s in state["sections"]][-3:], ["material_bom", "structure_bom", "bom_expenses"])
		self.assertEqual(sections["bom_expenses"]["total"], 7500)
		row = sections["material_bom"]["rows"][0]["name"]
		ops = [{"section": "material_bom", "row": row, "values": {"item": "BOM Test Lug", "qty": "40", "rate": "5"}}]
		portal_estimate.save_tab(est.name, ops=frappe.as_json(ops))
		self.assertEqual(flt(frappe.get_doc("Solar Design Estimate", est.name).material_bom[0].qty), 40)

	def test_the_proposal_and_quotation_show_them_as_the_estimate_has_them(self):
		from a3_sola.api import portal_proposal, quotation_option

		est = self.estimate()
		est.bom_expenses[0].rate = 8100
		est.save()
		self.assertIn("8,100", portal_proposal.estimate_boms(frappe.as_json([est.name])))
		bom = quotation_option.option_view(est.name)["bom"]
		for text in ("Material BOM", "Structure BOM", "BOM Test Flat Leg", "8,100"):
			self.assertIn(text, bom)
