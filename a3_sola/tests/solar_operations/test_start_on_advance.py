# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's first advance - any amount - starts Form 1, the stamp paper, the design freeze
and the structure material, each to the person its template names, else its position; a second
payment starts nothing again, and Form 1 Payment's due date follows Form 1."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from a3_sola.api import payment_tasks, stages, task_assignees
from a3_sola.setup.seed_stages import START_ON_ADVANCE
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_payment_tasks import ADV, PAID, ensure_firms, file_receipt


def person(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"user_type": "System User", "roles": [{"role": role}]}).insert(ignore_permissions=True)
	return email


class TestStartOnAdvance(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation().name
		inst = frappe.get_doc("Solar Installation", self.job)
		codes = {r.stage_code for r in inst.stages}
		if ADV not in codes or not set(START_ON_ADVANCE) <= codes:
			self.skipTest("the advance and its tasks are not on this site's template")
		ensure_firms(inst.company)
		self.ajay = person("advance.ajay@a3sola.test", "Solar Sales Coordinator")
		self.template = inst.stage_template
		self.before = dict(frappe.db.sql("""select stage_code, default_user from `tabInstallation Stage Template Detail`
			where parent=%s""", self.template))
		self.name_on_template("FRM1", self.ajay)

	def tearDown(self):
		frappe.set_user("Administrator")
		self.name_on_template("FRM1", self.before.get("FRM1"))

	def name_on_template(self, code, user):
		frappe.db.set_value("Installation Stage Template Detail", {"parent": self.template, "stage_code": code},
			"default_user", user, update_modified=False)

	def rows(self):
		return {r.stage_code: r for r in frappe.get_doc("Solar Installation", self.job).stages}

	def receive(self):
		file_receipt(self.job)
		payment_tasks.mark_received(self.job, ADV, **{**PAID, "amount": 5000})  # a 10% advance

	def test_the_first_advance_starts_the_work(self):
		pending = [c for c in START_ON_ADVANCE if self.rows()[c].status == "Pending"]
		self.assertTrue(pending, "a new job has these tasks pending")
		self.receive()
		rows = self.rows()
		for code in pending:
			self.assertEqual(rows[code].status, "In Progress", code)
			self.assertEqual(getdate(rows[code].actual_start_date), getdate(today()), code)
		frm1 = rows["FRM1"]
		if "FRM1" in pending:
			# The person the template names, not the position; due from today by its SLA.
			self.assertEqual(task_assignees.people(frappe.get_doc("Solar Installation", self.job), "FRM1"), [self.ajay])
			self.assertEqual(getdate(frm1.due_date), getdate(add_days(today(), int(frm1.sla_days))))
			self.assertTrue(frappe.db.exists("ToDo", {"allocated_to": self.ajay, "reference_name": self.job, "status": "Open"}))

	def test_a_second_payment_starts_nothing_again(self):
		self.receive()
		inst = frappe.get_doc("Solar Installation", self.job)
		self.assertEqual(stages.start_on_advance(inst), [])  # nothing is pending any more

	def test_a_skipped_or_done_task_is_left_alone(self):
		inst = frappe.get_doc("Solar Installation", self.job)
		row = next(r for r in inst.stages if r.stage_code == "STMP")
		row.status, row.skip_reason = "Skipped", "Bought already"
		started = stages.start_on_advance(inst)
		self.assertNotIn("STMP", [r.stage_code for r in started])
		self.assertEqual(row.status, "Skipped")

	def test_form_1_payment_follows_form_1(self):
		inst = frappe.get_doc("Solar Installation", self.job)
		f1pay = next(r for r in inst.stages if r.stage_code == "F1PAY")
		self.assertEqual(f1pay.due_anchor_task, "FRM1")
