# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task's documents are one list: a file on the task's record is its register row, and a
register row's file is on the task's record (api/task_files)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import task_files


class TestTaskFiles(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		row = frappe.db.get_value("Installation Stage Log", {"parenttype": "Solar Installation", "stage_code": "NPA",
			"task_document": ["is", "set"]}, ["parent", "task_doctype", "task_document"], as_dict=True)
		if not row:
			self.skipTest("No project with a Portal Registration document.")
		self.inst, self.doctype, self.name = frappe.get_doc("Solar Installation", row.parent), row.task_doctype, row.task_document
		self.url = frappe.get_doc({"doctype": "File", "file_name": "tf-test.txt", "content": b"test", "is_private": 1,
			"attached_to_doctype": "Solar Installation", "attached_to_name": self.inst.name}).insert(ignore_permissions=True).file_url

	def tearDown(self):
		frappe.db.rollback()

	def row(self, document):
		self.inst.reload()
		return next((r for r in self.inst.documents if r.stage_code == "NPA" and r.document_name == document), None)

	def test_a_general_type_is_the_row_it_means(self):
		self.assertEqual(task_files.register_name(self.inst, "NPA", "PM Surya Ghar Acknowledgement"), "Portal acknowledgement")
		self.assertEqual(task_files.register_name(self.inst, "NPA", "E-Token"), "E-Token")
		self.assertEqual(task_files.register_name(self.inst, "NPA", "Something New"), "Something New")
		self.assertIn("Portal acknowledgement", task_files.names_for(self.doctype, self.name))

	def test_a_file_on_the_record_is_the_tasks_document_and_goes_with_it(self):
		task_files.on_attached(self.doctype, self.name, "PM Surya Ghar Acknowledgement", self.url)
		self.assertEqual(self.row("Portal acknowledgement").attachment, self.url)
		task_files.on_removed(self.doctype, self.name, self.url)
		self.assertFalse(self.row("Portal acknowledgement").attachment)

	def test_a_file_on_the_panel_is_on_the_record_too(self):
		task_files.on_registered(self.inst, "NPA", "Feasibility Report", self.url)
		filed = frappe.db.get_value("File", {"attached_to_doctype": self.doctype, "attached_to_name": self.name,
			"file_url": self.url}, "a3s_document_type")
		self.assertEqual(filed, "Feasibility Report")
		task_files.on_unregistered(self.inst, "NPA", self.url)
		self.assertFalse(frappe.db.exists("File", {"attached_to_doctype": self.doctype, "attached_to_name": self.name,
			"file_url": self.url}))
