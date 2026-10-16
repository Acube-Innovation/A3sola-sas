# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Design Freeze: the job's BOMs are settled on its own page, and procurement follows."""

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

	def test_it_opens_its_own_page(self):
		self.assertTrue(tasks.open_task(self.job.name, "DSGN", create_draft=0)["url"].endswith("/tasks/DSGN"))
		state = design_freeze.state(self.job.name)
		for key in ("quotations", "survey", "structure_bom", "material_bom", "images", "procurement"):
			self.assertIn(key, state)

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

	def test_freezing_needs_both_boms_and_completes_the_task(self):
		job = frappe.get_doc("Solar Installation", self.job.name)
		if not (structure_bom.bom_for(job) and structure_bom.material_bom_for(job)):
			with self.assertRaises(frappe.ValidationError):
				design_freeze.freeze(self.job.name)
		self.job.db_set({"structure_bom": "BOM-S", "material_bom": "BOM-M"})
		with patch.object(structure_bom, "bom_items", return_value={"bom": None, "lines": []}), \
				patch.object(Document, "_validate_links", lambda self: None):
			state = design_freeze.freeze(self.job.name)
		self.assertEqual(state["task"]["status"], "Completed")
		self.assertEqual(state["frozen"], {"structure_bom": "BOM-S", "material_bom": "BOM-M"})

	def test_a_survey_of_another_customer_is_refused(self):
		other = frappe.get_all("Site Survey", filters={"solar_consumer": ["!=", self.job.solar_consumer]}, pluck="name", limit=1)
		if not other:
			self.skipTest("no other customer's survey on this site")
		with self.assertRaises(frappe.ValidationError):
			design_freeze.save(self.job.name, site_survey=other[0])
