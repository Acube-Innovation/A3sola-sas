# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Any task can be completed straight from the board: its assignee (or a manager) confirms
it is done, with a remark - nothing else to fill in on the task."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import task_assignees, tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import task_row


def plain_user(email):
	"""A desk user with no manager role."""
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"roles": [{"role": "Solar Operations Executive"}]}).insert(ignore_permissions=True)
	return email


class TestCompleteTask(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_remark_and_a_confirmation_complete_it(self):
		tasks.complete_from_board(self.installation.name, "FRM1", remarks="Signed offline", confirmed=1)
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual((row.status, row.completed_by), ("Completed", "Administrator"))
		self.assertTrue(row.actual_completion_date)
		self.assertIn("Signed offline", row.remarks)

	def test_no_remark_or_no_confirmation_no_completion(self):
		with self.assertRaises(frappe.ValidationError):
			tasks.complete_from_board(self.installation.name, "FRM1", remarks="", confirmed=1)
		with self.assertRaises(frappe.ValidationError):
			tasks.complete_from_board(self.installation.name, "FRM1", remarks="done", confirmed=0)
		row, _doc = task_row(self.installation, "FRM1")
		self.assertNotEqual(row.status, "Completed")

	def test_a_done_task_is_not_completed_again(self):
		tasks.complete_from_board(self.installation.name, "FRM1", remarks="done", confirmed=1)
		with self.assertRaises(frappe.ValidationError):
			tasks.complete_from_board(self.installation.name, "FRM1", remarks="again", confirmed=1)

	def test_only_the_assignee_or_a_manager(self):
		assignee, other = plain_user("assignee.ct@example.com"), plain_user("other.ct@example.com")
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		task_assignees.put(inst, "FRM1", [assignee])
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		inst.reload()
		self.assertTrue(tasks.may_complete(inst, "FRM1", assignee))
		self.assertFalse(tasks.may_complete(inst, "FRM1", other))
		self.assertTrue(tasks.may_complete(inst, "FRM1", "Administrator"))
