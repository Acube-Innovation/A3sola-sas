# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A person's work on their dashboard: their project tasks (as any of a task's people), lead
follow-ups, assignments and tickets, sorted into Pending (late, then undated), Today and the
next seven days; the team's only for a manager."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import my_work

ON = date(2026, 10, 30)


def work(due, title="x"):
	return {"kind": my_work.TASK, "title": title, "due": due}


class TestMyWork(FrappeTestCase):
	def test_work_is_sorted_by_when_it_is_due(self):
		b = my_work.buckets([
			work(date(2026, 10, 20), "late 10"), work(None, "undated"), work(date(2026, 10, 29), "late 1"),
			work(ON, "today"), work(date(2026, 11, 6), "in 7 days"), work(date(2026, 11, 2), "in 3 days"),
			work(date(2026, 11, 7), "in 8 days"),
		], on=ON)
		# Late first, oldest first, then what has no date yet.
		self.assertEqual([w["title"] for w in b["pending"]], ["late 10", "late 1", "undated"])
		self.assertEqual(b["pending"][0]["late_days"], 10)
		self.assertEqual([w["title"] for w in b["today"]], ["today"])
		self.assertEqual([w["title"] for w in b["upcoming"]], ["in 3 days", "in 7 days"])
		self.assertEqual(b["later"], 1)
		self.assertEqual(b["counts"], {"overdue": 2, "today": 1, "upcoming": 2, "undated": 1})

	def test_a_task_is_anyones_on_it_not_only_the_first(self):
		people = [frappe._dict(parent="JOB-1", stage_code="FRM1", user="first@x"),
			frappe._dict(parent="JOB-1", stage_code="FRM1", user="second@x")]
		rows = [frappe._dict(parent="JOB-1", stage_code="FRM1", stage_name="Form 1 Generation", status="In Progress",
				due_date=None, planned_date=date(2026, 11, 1), assigned_to="first@x", consumer_name="Anna"),
			frappe._dict(parent="JOB-1", stage_code="ADV", stage_name="Advance", status="Pending",
				due_date=date(2026, 10, 31), planned_date=None, assigned_to="other@x", consumer_name="Anna")]
		with patch.object(frappe.db, "sql", side_effect=[people, rows]):
			mine = my_work.project_tasks("second@x")
		self.assertEqual([w["title"] for w in mine], ["Form 1 Generation"])
		# Not started, so not due yet: due when the plan has it end.
		self.assertEqual(mine[0]["due"], date(2026, 11, 1))
		self.assertTrue(mine[0]["url"].endswith("/tasks/FRM1"))
		with patch.object(frappe.db, "sql", side_effect=[people, rows]):
			self.assertEqual(len(my_work.project_tasks("second@x", team=True)), 2)

	def test_a_todo_that_repeats_listed_work_is_left_out(self):
		task = frappe._dict(reference_type="Solar Installation", description="[FRM1] Form 1 Generation")
		digest = frappe._dict(reference_type="Lead", description="3 solar leads are due for follow-up in X: a, b")
		survey = frappe._dict(reference_type="Solar Consumer", description="Book the site survey slot.")
		self.assertTrue(my_work._is_duplicate(task))
		self.assertTrue(my_work._is_duplicate(digest))
		self.assertFalse(my_work._is_duplicate(survey))

	def test_the_team_is_a_managers(self):
		with patch.object(frappe, "get_roles", return_value=["Solar Sales Coordinator", "Employee"]):
			self.assertFalse(my_work.is_manager("someone@x"))
		with patch.object(frappe, "get_roles", return_value=["Solar Project Manager"]):
			self.assertTrue(my_work.is_manager("boss@x"))

	def test_a_followup_is_its_owners(self):
		leads = [frappe._dict(name="L1", lead_name="Anna", next_followup_date=date(2026, 10, 29), status="Interested",
				lead_owner="me@x", owner="admin@x", mobile_no="9"),
			frappe._dict(name="L2", lead_name="Ben", next_followup_date=date(2026, 10, 29), status="Open",
				lead_owner=None, owner="other@x", mobile_no=None)]
		with patch.object(frappe, "get_all", return_value=leads):
			self.assertEqual([w["title"] for w in my_work.lead_follow_ups("me@x")], ["Follow up: Anna"])
