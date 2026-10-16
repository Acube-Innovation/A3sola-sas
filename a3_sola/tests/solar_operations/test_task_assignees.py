# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A project's tasks start with their default people - the person in each task's position
on the job - and take any number of people after that."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import task_assignees as ta
from a3_sola.tests.solar_operations.fixtures import make_installation


def user(email, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"user_type": "System User", "roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)
	return email


class TestTaskAssignees(FrappeTestCase):
	def setUp(self):
		self.engineer = user("assign.engineer@example.com")
		self.engineer2 = user("assign.engineer2@example.com")
		self.manager = user("assign.manager@example.com")
		self.installation = make_installation()

	def job(self):
		return frappe.get_doc("Solar Installation", self.installation.name)

	def staff(self, **people):
		doc = self.job()
		doc.update(people)
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		return self.job()

	def test_the_template_names_each_tasks_default(self):
		template = frappe.get_doc("Installation Stage Template", self.installation.stage_template)
		defaults = {r.stage_code: r.default_assignee for r in template.stages}
		self.assertEqual(defaults.get("ADV"), "Lead Owner")
		self.assertEqual(defaults.get("BAL"), "Accounts")
		self.assertEqual(defaults.get("FRM1"), "Sales Co-ordinator")
		self.assertEqual(defaults.get("SUBREQ"), "Project Manager")
		self.assertEqual(defaults.get("IWOS"), "Contractor")
		self.assertEqual(defaults.get("DSGN"), "Project Engineer")

	def test_tasks_go_to_the_people_named_on_the_job(self):
		doc = self.staff(site_engineer=self.engineer, project_manager=self.manager)
		self.assertEqual(ta.people(doc, "DSGN"), [self.engineer])
		self.assertEqual(ta.people(doc, "IWOS"), [self.engineer], "a contractor's task is the engineer's")
		self.assertEqual(ta.people(doc, "SUBREQ"), [self.manager])
		row = next(r for r in doc.stages if r.stage_code == "DSGN")
		self.assertEqual((row.assigned_to, row.default_assignee), (self.engineer, "Project Engineer"))

	def test_accounts_is_everyone_in_accounts(self):
		with patch.object(ta, "role_holders", return_value=["a@example.com", "b@example.com"]):
			self.assertEqual(ta.resolve(self.job(), "Accounts"), ["a@example.com", "b@example.com"])

	def test_a_task_takes_several_people_the_first_leading(self):
		ta.set_task_assignees(self.installation.name, "DSGN", [self.engineer2, self.engineer])
		doc = self.job()
		self.assertEqual(ta.people(doc, "DSGN"), [self.engineer2, self.engineer])
		self.assertEqual(next(r for r in doc.stages if r.stage_code == "DSGN").assigned_to, self.engineer2)

	def test_a_new_engineer_takes_over_the_open_tasks_only(self):
		doc = self.staff(site_engineer=self.engineer)
		ta.set_task_assignees(self.installation.name, "PROC", [self.engineer, self.manager])
		done = next(r for r in doc.stages if r.stage_code == "ORD")
		self.assertIn(done.status, ("Completed", "Pending", "In Progress"))
		doc = self.job()
		for r in doc.stages:
			if r.stage_code == "DSGN":
				r.status = "Completed"
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		doc = self.staff(site_engineer=self.engineer2)
		self.assertEqual(ta.people(doc, "PROC"), [self.engineer2, self.manager], "the extra person stays")
		self.assertEqual(ta.people(doc, "DSGN"), [self.engineer], "a completed task keeps who did it")

	def test_the_tasks_document_adds_its_person(self):
		doc = self.staff(site_engineer=self.engineer)
		row = next(r for r in doc.stages if r.stage_code == "DSGN")
		ta.add(doc, row.stage_code, self.manager)
		self.assertEqual(ta.people(doc, "DSGN"), [self.engineer, self.manager])

	def test_an_edited_default_survives_a_reseed(self):
		from a3_sola.setup import install_ops

		name = frappe.db.get_value("Installation Stage Template Detail",
			{"parent": self.installation.stage_template, "stage_code": "BAL"}, "name")
		was = frappe.db.get_value("Installation Stage Template Detail", name, "default_assignee")
		frappe.db.set_value("Installation Stage Template Detail", name, "default_assignee", "Project Manager")
		try:
			install_ops.seed_stage_templates()
			self.assertEqual(frappe.db.get_value("Installation Stage Template Detail", name, "default_assignee"), "Project Manager")
		finally:
			# The class rolls back only at its end: put the default back for the tests after.
			frappe.db.set_value("Installation Stage Template Detail", name, "default_assignee", was)

	def test_the_task_shows_its_people_and_its_document_starts_with_the_lead(self):
		from a3_sola.api import tasks
		from a3_sola.www.a3solaportal.collections import task_people

		self.staff(site_engineer=self.engineer)
		# The Design Freeze has its own page now (api/design_freeze); structure procurement opens a task.
		ta.set_task_assignees(self.installation.name, "SPROC", [self.engineer, self.manager])
		people = task_people(self.installation.name, "SPROC")
		self.assertEqual([p["user"] for p in people["assignees"]], [self.engineer, self.manager])
		self.assertEqual(people["position"], "Project Engineer")
		target = tasks.open_task(self.installation.name, "SPROC", create_draft=0)
		self.assertEqual(target["route_options"]["assigned_to"], self.engineer)
