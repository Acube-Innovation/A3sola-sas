# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The material BOM follows the job's inverter: the one A3 Sola Settings lists for its phase and
capacity, with the job's own panels added, and freezing keeps both on the job."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import design_freeze, structure_bom
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.test_quotation import ensure_item

ROWS = [
	{"inverter_capacity_kw": 3, "bom": "BOM-K3"},
	{"inverter_capacity_kw": 5, "bom": "BOM-K5"},
]


def job(kw, phase="Single Phase", nos=1, panels=()):
	doc = frappe.get_doc({"doctype": "Solar Installation", "connection_type": phase})
	doc.append("inverters", {"inverter_capacity_kw": kw, "nos": nos, "inverter_phase": phase, "is_option": 0})
	doc.append("inverters", {"inverter_capacity_kw": 99, "nos": 1, "inverter_phase": phase, "is_option": 1})
	for row in panels:
		doc.append("panels", row)
	return doc


class TestInverterCapacityBOM(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_the_bom_is_picked_by_the_chosen_inverter(self):
		with patch.object(frappe, "get_all", return_value=[{"panel_capacity_kw": r["inverter_capacity_kw"], "bom": r["bom"]} for r in ROWS]):
			self.assertEqual(structure_bom.capacity_bom_for(job(3)), "BOM-K3")
			# Next larger, then the largest; an option row does not count.
			self.assertEqual(structure_bom.capacity_bom_for(job(4)), "BOM-K5")
			self.assertEqual(structure_bom.capacity_bom_for(job(10)), "BOM-K5")
			# Three micro inverters of 1 kW are a 3 kW inverter.
			self.assertEqual(structure_bom.capacity_bom_for(job(1, nos=3)), "BOM-K3")
		self.assertEqual(structure_bom.job_inverter(job(1, "Three Phase", nos=8)), ("Three Phase", 8))

	def test_the_frozen_bom_comes_first_then_the_inverters(self):
		doc = job(3)
		with patch.object(structure_bom, "capacity_bom_for", return_value="BOM-K3"):
			self.assertEqual(structure_bom.material_bom_for(doc), "BOM-K3")
			doc.material_bom = "BOM-JOB"
			self.assertEqual(structure_bom.material_bom_for(doc), "BOM-JOB")

	def test_the_jobs_panels_are_its_lines(self):
		doc = job(3, panels=[
			{"panel_capacity_wp": 545, "panel_count": 6, "panel_type": "DCR", "is_option": 0},
			{"panel_capacity_wp": 777, "panel_count": 4, "panel_type": "DCR", "is_option": 0},
			{"panel_capacity_wp": 545, "panel_count": 9, "panel_type": "DCR", "is_option": 1},
		])
		code = ensure_item("Test Panel 545 Wp")
		with patch.object(structure_bom, "panel_item", side_effect=lambda make, wp, dcr, technology=None: code if wp == 545 else None):
			lines = structure_bom.panel_lines(doc)
		self.assertEqual([(l["item_code"], l["qty"]) for l in lines], [(code, 6), ("", 4)])
		# A panel with no module Item is shown, to be chosen.
		self.assertTrue(lines[1]["note"])

	def test_a_panel_item_is_its_make_and_wp(self):
		group = frappe.db.get_value("Item Group", {"name": ["in", ["Mono PERC Modules", "Modules"]], "is_group": 0})
		if not group:
			self.skipTest("no module item group")
		if not frappe.db.exists("Brand", "Testpanel"):
			frappe.get_doc({"doctype": "Brand", "brand": "Testpanel"}).insert()
		if not frappe.db.exists("Item", "TEST-MOD-545"):
			frappe.get_doc({"doctype": "Item", "item_code": "TEST-MOD-545", "item_name": "Testpanel 545 Wp Module",
				"item_group": group, "stock_uom": "Nos", "brand": "Testpanel"}).insert()
		self.assertEqual(structure_bom.panel_item("Testpanel Non-DCR", 545, False), "TEST-MOD-545")
		self.assertIsNone(structure_bom.panel_item("Testpanel", 600))

	def test_freezing_keeps_the_panels_with_the_bom(self):
		inst = make_installation()
		kit, cable, panel = ensure_item("Test Material Kit"), ensure_item("Test AC Cable"), ensure_item("Test Panel 550 Wp")
		template = frappe.get_doc({"doctype": "BOM", "item": kit, "company": inst.company, "quantity": 1,
			"items": [{"item_code": cable, "qty": 12}]}).insert()
		template.submit()
		panel_line = {"item_code": panel, "item_name": panel, "description": "", "qty": 6, "uom": "Nos", "note": ""}
		with patch.object(structure_bom, "capacity_boms", return_value={template.name}), \
				patch.object(structure_bom, "capacity_bom_for", return_value=template.name), \
				patch.object(structure_bom, "panel_lines", return_value=[panel_line]):
			frozen = design_freeze.freeze(inst.name)["frozen"]["material_bom"]
		self.assertNotEqual(frozen, template.name)
		bom = frappe.get_doc("BOM", frozen)
		self.assertEqual(sorted((r.item_code, r.qty) for r in bom.items), sorted([(cable, 12), (panel, 6)]))
		self.assertEqual(bom.is_default, 0)


class TestPanelCapacityStructureBOM(FrappeTestCase):
	"""The structure BOM follows the roof and the panel capacity: the package's own first, else the
	one A3 Sola Settings lists."""

	def rows(self, package_rows):
		settings = [{"panel_capacity_kw": 3, "bom": "BOM-FLAT-3"}, {"panel_capacity_kw": 5, "bom": "BOM-FLAT-5"}]
		return lambda doctype, **kw: package_rows if doctype == "Solar Package Structure BOM" else settings

	def job(self, kw, package="PKG"):
		return frappe._dict({"roof_type": "ROOF", "capacity_kw": kw, "solar_package": package, "structure_bom": None})

	def test_settings_by_panel_capacity_when_the_package_has_none(self):
		with patch.object(frappe, "get_all", side_effect=self.rows([])):
			self.assertEqual(structure_bom.bom_for(self.job(2.5)), "BOM-FLAT-3")
			self.assertEqual(structure_bom.bom_for(self.job(3.3)), "BOM-FLAT-5")
			self.assertEqual(structure_bom.bom_for(self.job(9, package=None)), "BOM-FLAT-5")

	def test_the_packages_own_comes_first(self):
		with patch.object(frappe, "get_all", side_effect=self.rows([{"panel_capacity_kw": 3, "bom": "BOM-PKG"}])):
			self.assertEqual(structure_bom.bom_for(self.job(3)), "BOM-PKG")
