# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Structure Material Procurement: the task sits between Design Freeze and the structure
work order, and shows the package's structure BOM for the project's roof type and size."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import structure_bom
from a3_sola.setup import seed_stages
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestStructureBOM(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_the_bom_is_the_exact_size_else_the_next_larger_else_the_largest(self):
		rows = [{"panel_capacity_kw": 3, "bom": "B3"}, {"panel_capacity_kw": 5, "bom": "B5"}, {"panel_capacity_kw": 10, "bom": "B10"}]
		self.assertEqual(structure_bom.pick(rows, 5), "B5")
		self.assertEqual(structure_bom.pick(rows, 4.2), "B5")
		self.assertEqual(structure_bom.pick(rows, 1.44), "B3")
		self.assertEqual(structure_bom.pick(rows, 12), "B10")
		self.assertIsNone(structure_bom.pick([], 5))

	def test_the_project_takes_its_own_roof_types_bom(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		roofs = frappe.get_all("Roof Type", pluck="name", limit=2)
		if len(roofs) < 2 or not inst.solar_package:
			self.skipTest("needs two roof types and a package")
		package = frappe.get_doc("Solar Package", inst.solar_package)
		package.set("structure_boms", [
			{"roof_type": roofs[0], "panel_capacity_kw": 50, "bom": "BOM-MINE"},
			{"roof_type": roofs[1], "panel_capacity_kw": 50, "bom": "BOM-OTHER"},
		])
		package.flags.ignore_links = True
		package.save(ignore_permissions=True)
		frappe.db.set_value("Solar Installation", inst.name, "roof_type", roofs[0])
		self.assertEqual(structure_bom.bom_for(inst.name), "BOM-MINE")
		choices = structure_bom.choices_for(frappe._dict(solar_installation=inst.name))
		self.assertEqual({c["value"] for c in choices}, {"BOM-MINE", "BOM-OTHER"})

	def test_a_new_project_has_the_task_after_design_freeze_and_the_orders_after_dispatch(self):
		codes = [r.stage_code for r in frappe.get_doc("Solar Installation", self.installation.name).stages]
		self.assertIn("SPROC", seed_stages.TASK_CODES)
		self.assertEqual(codes[codes.index("DSGN") + 1], "SPROC")
		# The work orders follow the dispatch: the material is on site before the crews are.
		self.assertEqual(codes[codes.index("DISP") + 1: codes.index("DISP") + 3], ["IWOS", "IWOI"])

	def test_the_engineer_completes_it_with_nothing_more_to_show(self):
		from a3_sola.solar_operations.doctype.installation_task.installation_task import complete

		task = frappe.get_doc({"doctype": "Installation Task", "solar_installation": self.installation.name,
			"task_code": "SPROC"})
		task.flags.ignore_permissions = True
		task.insert(ignore_permissions=True)
		complete(task.name)
		row = next(r for r in frappe.get_doc("Solar Installation", self.installation.name).stages if r.stage_code == "SPROC")
		self.assertEqual(row.status, "Completed")
		self.assertTrue(frappe.db.get_value("Installation Task", task.name, "structure_procured_on"))

	def test_an_existing_project_takes_the_task_after_design_freeze(self):
		from a3_sola.patches.v1_2 import structure_material_task as patch

		inst = frappe.get_doc("Solar Installation", self.installation.name)
		inst.set("stages", [r for r in inst.stages if r.stage_code != "SPROC"])
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		template = frappe.get_doc("Installation Stage Template", inst.stage_template)
		source = next(r for r in template.stages if r.stage_code == "SPROC")
		inst = frappe.get_doc("Solar Installation", inst.name)
		patch._insert(inst, source, [r.stage_code for r in inst.stages].index("DSGN") + 1)
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		codes = [r.stage_code for r in frappe.get_doc("Solar Installation", inst.name).stages]
		self.assertEqual(codes[codes.index("DSGN") + 1], "SPROC")

	def test_the_material_list_fills_from_the_bom(self):
		from unittest.mock import patch

		lines = {"bom": "BOM-X", "lines": [
			{"item_code": "ITEM-A", "item_name": "Pipe A", "description": "", "qty": 3, "uom": "Nos"},
			{"item_code": "ITEM-B", "item_name": "Bolt B", "description": "", "qty": 18, "uom": "Nos"},
		]}
		task = frappe.new_doc("Installation Task")
		task.update({"task_code": "SPROC", "structure_bom": "BOM-X"})
		with patch.object(structure_bom, "bom_items", return_value=lines):
			structure_bom.fill_materials(task)
		self.assertEqual([(r.material, r.qty, r.item_code) for r in task.structure_materials],
			[("Pipe A", 3, "ITEM-A"), ("Bolt B", 18, "ITEM-B")])

	def test_the_task_keeps_its_name_and_the_list_as_edited(self):
		from a3_sola.api import portal_crud

		made = portal_crud.create_record(
			slug="installation-tasks", source_dt="Solar Installation", source=self.installation.name, source_task="SPROC",
			__items=frappe.as_json([
				{"material": "Pipe A", "qty": 4, "uom": "Nos"},
				{"material": "Hacksaw blade", "qty": 2, "uom": "Nos"},
			]),
		)
		task = frappe.get_doc("Installation Task", made["name"])
		self.assertEqual(task.task_name, "Structure Material Procurement")
		self.assertEqual([(r.material, r.qty) for r in task.structure_materials], [("Pipe A", 4), ("Hacksaw blade", 2)])

	def test_the_material_grid_is_the_structure_tasks_only(self):
		from a3_sola.www.a3solaportal.collections import item_table

		self.assertIsNotNone(item_table("installation-tasks", frappe._dict(task_code="SPROC", structure_materials=[])))
		self.assertIsNone(item_table("installation-tasks", frappe._dict(task_code="ADV")))
		self.assertIsNone(item_table("installation-tasks"))

	def test_it_is_due_when_the_advance_is(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		adv = next(r for r in inst.stages if r.stage_code == "ADV")
		adv.status, adv.due_date = "In Progress", frappe.utils.add_days(frappe.utils.today(), 4)
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		inst.reload()
		sproc = next(r for r in inst.stages if r.stage_code == "SPROC")
		self.assertEqual(sproc.due_anchor_task, "ADV")
		self.assertEqual(str(sproc.due_date), str(next(r for r in inst.stages if r.stage_code == "ADV").due_date))

	def test_the_purchase_list_prints_the_package_bom_then_the_structure_material(self):
		from io import BytesIO

		from pypdf import PdfReader

		from a3_sola.api import purchase_list
		from a3_sola.www.a3solaportal.collections import task_downloads

		frappe.db.set_value("Solar Installation", self.installation.name, {"latitude": 10.307, "longitude": 76.333})
		task = frappe.get_doc({"doctype": "Installation Task", "solar_installation": self.installation.name,
			"task_code": "SPROC", "structure_materials": [{"material": "Anchor Bolt", "qty": 18, "uom": "Nos"}]})
		task.flags.ignore_permissions = True
		task.insert(ignore_permissions=True)
		parts = purchase_list.lines(task)
		self.assertEqual((parts["title"], parts["rows"]), ("Structure Material", [{"material": "Anchor Bolt", "uom": "Nos", "qty": 18}]))

		purchase_list.pdf(task.name)
		reader = PdfReader(BytesIO(frappe.local.response.filecontent))
		text = " ".join(" ".join(p.extract_text() for p in reader.pages).split())
		for expected in ("BILL TO", "SHIP TO", "Anchor Bolt", "Structure Material"):
			self.assertIn(expected, text)
		uris = [a.get_object()["/A"]["/URI"] for p in reader.pages for a in (p.get("/Annots") or [])]
		self.assertTrue(any("google.com/maps" in u and "10.307" in u for u in uris))

		self.assertEqual(task_downloads(self.installation.name, "SPROC", task.name)[0]["url"], purchase_list.url(task.name, download=True))
		self.assertEqual(task_downloads(self.installation.name, "SPROC"), [], "nothing to print before the task is saved")

	def test_material_procurement_is_worked_on_its_own_task_with_the_package_bom(self):
		from unittest.mock import patch

		from a3_sola.api import purchase_list, tasks

		row = next(r for r in frappe.get_doc("Solar Installation", self.installation.name).stages if r.stage_code == "PROC")
		self.assertEqual(row.task_doctype, "Installation Task")
		target = tasks.open_task(self.installation.name, "PROC", create_draft=0)
		self.assertEqual((target["doctype"], target["route_options"]["task_code"]), ("Installation Task", "PROC"))

		lines = {"bom": "BOM-P", "lines": [{"item_code": "P1", "item_name": "Panel 550Wp", "description": "", "qty": 6, "uom": "Nos"}]}
		task = frappe.new_doc("Installation Task")
		task.update({"task_code": "PROC", "material_bom": "BOM-P"})
		with patch.object(structure_bom, "bom_items", return_value=lines):
			structure_bom.fill_materials(task)
		self.assertEqual([(r.material, r.qty) for r in task.materials], [("Panel 550Wp", 6)])
		self.assertEqual(purchase_list.lines(task)["title"], "Material")


	def test_the_tasks_remarks_go_out_with_its_purchase_list(self):
		from a3_sola.api import purchase_list

		structure = frappe._dict(task_code="SPROC", structure_notes="Use 16 G only", remarks="Deliver before 20 Oct", structure_materials=[])
		self.assertEqual(purchase_list.lines(structure)["remarks"], ["Use 16 G only", "Deliver before 20 Oct"])
		material = frappe._dict(task_code="PROC", remarks="  ", materials=[])
		self.assertEqual(purchase_list.lines(material)["remarks"], [])
