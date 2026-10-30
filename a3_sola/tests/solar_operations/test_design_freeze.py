# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The design freezes: Solar Design Freeze settles the structure and material BOMs, Structural
Design Freeze the structure BOM, each on its own page, and procurement follows. A BOM's lines
edited on the page become the job's own BOM."""

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import design_freeze, structure_bom, tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.test_quotation import ensure_item

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
		for key in ("quotations", "survey", "structure_bom", "material_bom", "images", "procurement"):
			self.assertIn(key, solar)
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

	def test_edited_lines_become_the_jobs_own_bom(self):
		pipe, bolt = ensure_item("Design Test Pipe"), ensure_item("Design Test Bolt")
		lines = frappe.as_json([{"item_code": pipe, "qty": 4}, {"item_code": bolt, "qty": 0}])
		first = design_freeze.save_lines(self.job.name, "structure_bom", lines)["structure_bom"]
		bom = frappe.get_doc("BOM", first["value"])
		self.assertEqual((bom.docstatus, bom.is_default), (1, 0))
		# A line at 0 is dropped; the job holds the new BOM.
		self.assertEqual([(r.item_code, r.qty) for r in bom.items], [(pipe, 4)])
		self.assertEqual(frappe.db.get_value("Solar Installation", self.job.name, "structure_bom"), bom.name)

		lines = frappe.as_json([{"item_code": pipe, "qty": 6}, {"item_code": bolt, "qty": 20}])
		second = design_freeze.save_lines(self.job.name, "structure_bom", lines)["structure_bom"]
		self.assertNotEqual(second["value"], bom.name)
		self.assertEqual([(r["item_code"], r["qty"]) for r in second["lines"]], [(pipe, 6), (bolt, 20)])
		# The job's earlier edit, held by nothing now, goes inactive.
		self.assertEqual(frappe.db.get_value("BOM", bom.name, "is_active"), 0)

	def test_an_empty_or_repeated_list_is_refused(self):
		pipe = ensure_item("Design Test Pipe")
		with self.assertRaises(frappe.ValidationError):
			design_freeze.save_lines(self.job.name, "material_bom", "[]")
		with self.assertRaises(frappe.ValidationError):
			design_freeze.save_lines(self.job.name, "material_bom",
				frappe.as_json([{"item_code": pipe, "qty": 1}, {"item_code": pipe, "qty": 2}]))
