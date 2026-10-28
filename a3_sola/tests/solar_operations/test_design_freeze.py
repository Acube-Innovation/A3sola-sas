# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The design freezes: Solar Design Freeze settles the material BOM, Structural Design Freeze the
structure BOM, each on its own page, and procurement follows."""

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import design_freeze, structure_bom, tasks
from a3_sola.tests.solar_operations.fixtures import make_installation

LINES = {"bom": "BOM-NEW", "lines": [
	{"item_code": "ITEM-A", "item_name": "Pipe A", "description": "", "qty": 7, "uom": "Nos"},
]}


class TestDesignFreeze(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation()

	def test_each_opens_its_own_page_with_its_own_side(self):
		for code in ("DSGN", "SDSGN"):
			self.assertTrue(tasks.open_task(self.job.name, code, create_draft=0)["url"].endswith("/tasks/" + code))
		solar = design_freeze.state(self.job.name)
		self.assertEqual(solar["task"]["name"], "Solar Design Freeze")
		for key in ("quotations", "survey", "material_bom", "images", "procurement"):
			self.assertIn(key, solar)
		self.assertNotIn("structure_bom", solar)
		structural = design_freeze.state(self.job.name, "SDSGN")
		self.assertEqual(structural["task"]["name"], "Structural Design Freeze")
		self.assertIn("structure_bom", structural)
		self.assertNotIn("material_bom", structural)
		self.assertEqual(structural["sld"]["name"], "Structure drawing")

	def test_the_jobs_boms_come_before_the_packages(self):
		self.job.db_set({"structure_bom": "BOM-S", "material_bom": "BOM-M"})
		job = frappe.get_doc("Solar Installation", self.job.name)
		self.assertEqual(structure_bom.bom_for(job), "BOM-S")
		self.assertEqual(structure_bom.material_bom_for(job), "BOM-M")
		self.assertEqual(tasks._installation_task_route(job, "SPROC")["structure_bom"], "BOM-S")
		self.assertEqual(tasks._installation_task_route(job, "PROC")["material_bom"], "BOM-M")

	def test_a_draft_procurement_task_follows_a_changed_bom(self):
		from a3_sola.api import portal_crud

		made = portal_crud.create_record(slug="installation-tasks", source_dt="Solar Installation",
			source=self.job.name, source_task="SPROC")
		self.job.db_set("structure_bom", "BOM-NEW")
		with patch.object(structure_bom, "bom_items", return_value=LINES), \
				patch.object(Document, "_validate_links", lambda self: None):
			updated = design_freeze.refresh_procurement(frappe.get_doc("Solar Installation", self.job.name))
		self.assertIn(made["name"], updated)
		task = frappe.get_doc("Installation Task", made["name"])
		self.assertEqual(task.structure_bom, "BOM-NEW")
		self.assertEqual([(r.material, r.qty) for r in task.structure_materials], [("Pipe A", 7)])

	def test_each_freeze_needs_only_its_own_bom_and_completes_only_its_task(self):
		self.job.db_set({"material_bom": "BOM-M"})
		with patch.object(structure_bom, "bom_items", return_value={"bom": None, "lines": []}), \
				patch.object(Document, "_validate_links", lambda self: None):
			solar = design_freeze.freeze(self.job.name)
		self.assertEqual(solar["task"]["status"], "Completed")
		self.assertEqual(solar["frozen"]["material_bom"], "BOM-M")
		self.assertNotEqual(design_freeze.state(self.job.name, "SDSGN")["task"]["status"], "Completed")

		self.job.db_set({"structure_bom": "BOM-S"})
		with patch.object(structure_bom, "bom_items", return_value={"bom": None, "lines": []}), \
				patch.object(Document, "_validate_links", lambda self: None):
			structural = design_freeze.freeze(self.job.name, "SDSGN")
		self.assertEqual(structural["task"]["status"], "Completed")
		self.assertEqual(structural["frozen"], {"structure_bom": "BOM-S", "material_bom": "BOM-M"})

	def test_the_structural_freeze_needs_a_structure_bom(self):
		with patch.object(structure_bom, "bom_for", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				design_freeze.freeze(self.job.name, "SDSGN")

	def test_a_survey_of_another_customer_is_refused(self):
		other = frappe.get_all("Site Survey", filters={"solar_consumer": ["!=", self.job.solar_consumer]}, pluck="name", limit=1)
		if not other:
			self.skipTest("no other customer's survey on this site")
		with self.assertRaises(frappe.ValidationError):
			design_freeze.save(self.job.name, site_survey=other[0])
