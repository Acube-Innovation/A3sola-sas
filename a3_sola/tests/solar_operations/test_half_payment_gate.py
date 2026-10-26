# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Structure and material work, its dispatch and work orders, the serials, Forms 2 and 3 and the
balance request wait for half the project value confirmed by Accounts - unless an Operations
Manager exempts the job. Half in (or exempt), the first steps start; each step starts the next."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import payment_tasks, stages, tasks
from a3_sola.setup.seed_stages import HALF_PAID_TASKS, START_ON_ADVANCE
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_payment_tasks import ADV, PAID, ensure_firms


def plain_user(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"user_type": "System User", "roles": [{"role": role}]}).insert(ignore_permissions=True)
	return email


class TestHalfPaymentGate(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation(half_paid_gate=True).name
		codes = {r.stage_code for r in self.inst().stages}
		if not {"SPROC", "PROC", "DISP", ADV} <= codes:
			self.skipTest("the held tasks are not on this site's template")

	def tearDown(self):
		frappe.set_user("Administrator")

	def inst(self):
		return frappe.get_doc("Solar Installation", self.job)

	def status(self, code):
		return next(r.status for r in self.inst().stages if r.stage_code == code)

	def test_the_held_work_is_refused_below_half(self):
		inst = self.inst()
		self.assertLess(stages.paid_share(inst), 50)
		self.assertIn("50%", stages.half_paid_lock(inst, "PROC"))
		self.assertIsNone(stages.half_paid_lock(inst, "FRM1"), "Form 1 is not held")
		for code in ("PROC", "SPROC"):
			with self.assertRaises(frappe.ValidationError):
				tasks.open_task(self.job, code, create_draft=0)
		with self.assertRaises(frappe.ValidationError):
			tasks.complete_task(self.job, "PROC", remarks="done")

	def test_the_board_shows_it_locked(self):
		from a3_sola.www.a3solaportal.project_overview import project_overview

		overview = project_overview(self.inst())
		cards = {t["code"]: t for col in overview["columns"] for t in col["tasks"]}
		self.assertTrue(cards["PROC"]["locked"])
		self.assertFalse(cards["PROC"]["can_complete"])
		self.assertFalse(overview["half_paid"]["open"])

	def test_a_manager_exempts_and_the_work_starts(self):
		stages.exempt_half_payment(self.job, "Customer is a repeat client")
		inst = self.inst()
		self.assertTrue(inst.half_payment_exempt)
		self.assertEqual(inst.half_payment_exempt_by, "Administrator")
		for code in ("SPROC", "PROC"):
			self.assertEqual(self.status(code), "In Progress", code)
		self.assertIsNone(stages.half_paid_lock(inst, "DISP"))

	def test_only_a_manager_exempts(self):
		frappe.set_user(plain_user("halfpay.coordinator@a3sola.test", "Solar Sales Coordinator"))
		with self.assertRaises(frappe.PermissionError):
			stages.exempt_half_payment(self.job, "Please")

	def test_half_confirmed_starts_the_work(self):
		from unittest.mock import patch

		from a3_sola.api import billing
		from a3_sola.tests.solar_operations.test_portal_tasks import posted
		from a3_sola.tests.solar_projects.fixtures import installation_with_customer

		# A job with a customer and a billing plan, as payments are recorded against.
		self.job = installation_with_customer(half_paid_gate=True).name
		ensure_firms(self.inst().company)
		self.assertTrue(billing.ensure_plan_for_installation(self.job, replay=False))

		def pay(amount, reference):
			with patch.object(frappe, "request", posted(f"ADV-{reference}.txt", f"ADV {amount}".encode())):
				payment_tasks.mark_received(self.job, ADV, amount=amount, reference=reference, bank=PAID["bank"], company=PAID["company"])

		pay(50000, "UTR1")  # 23%: not yet
		payment_tasks.confirm(self.job, ADV)
		self.assertEqual(self.status("PROC"), "Pending")
		pay(60000, "UTR2")  # 51% once confirmed
		self.assertEqual(self.status("PROC"), "Pending", "marked is not confirmed")
		payment_tasks.confirm(self.job, ADV)
		self.assertGreaterEqual(stages.paid_share(self.inst()), 50)
		for code in ("SPROC", "PROC"):
			self.assertEqual(self.status(code), "In Progress", code)

	def test_each_step_starts_the_next(self):
		stages.exempt_half_payment(self.job, "Test")
		inst = self.inst()
		for row in inst.stages:
			if row.stage_code == "SPROC":
				row.status = "Completed"
		self.assertEqual(stages.start_next(inst, "SPROC"), [], "dispatch waits for material too")
		for row in inst.stages:
			if row.stage_code == "PROC":
				row.status = "Completed"
		self.assertEqual([r.stage_code for r in stages.start_next(inst, "PROC")], ["DISP"])

	def test_the_advance_no_longer_starts_structure_material(self):
		self.assertNotIn("SPROC", START_ON_ADVANCE)
		self.assertIn("SPROC", HALF_PAID_TASKS)
