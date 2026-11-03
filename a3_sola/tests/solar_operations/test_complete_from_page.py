# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Complete task on a task's own page: its required documents first, then its document done
as its task reads it, and the task with it (tasks.complete_from_page)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.api import tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import make_task, task_row


class TestCompleteFromPage(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def tearDown(self):
		frappe.db.rollback()

	def test_a_task_is_completed_with_its_document(self):
		task = make_task(self.installation, "ADV", amount=1000, paid_on=today())
		r = tasks.complete_from_page("installation-tasks", task.name)
		self.assertIn("/projects/", r["route"])
		row, _inst = task_row(self.installation, "ADV")
		self.assertEqual(row.status, "Completed")
		task.reload()
		self.assertEqual((task.docstatus, task.status), (1, "Completed"))
		# Once done, completing again just goes back to the project.
		self.assertTrue(tasks.complete_from_page("installation-tasks", task.name).get("already"))

	def test_a_task_waits_for_its_required_documents(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertIn("DCR certificate", tasks.missing_documents(inst, "PORTUPD"))
		task = make_task(self.installation, "PORTUPD")
		with self.assertRaises(frappe.ValidationError):
			tasks.complete_from_page("installation-tasks", task.name)
		row, _inst = task_row(self.installation, "PORTUPD")
		self.assertNotEqual(row.status, "Completed")
