# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Asking for the advance until it comes (api/payment_followup): Form 1 ahead of the advance
on a job the customer pays, the customer asked once it is submitted, the bank some days after
the loan is sanctioned, each ask logged and a to-do on the day the next is due."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from a3_sola.api import payment_followup, stages, tasks
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestPaymentFollowUp(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.inst = make_installation()
		# Something left to ask for, whatever the job's terms.
		self.owed = patch.object(payment_followup, "outstanding", return_value=150000)
		self.owed.start()
		self.people = patch("a3_sola.api.task_assignees.people", return_value=["Administrator"])
		self.people.start()

	def tearDown(self):
		self.people.stop()
		self.owed.stop()
		frappe.db.rollback()

	def row(self, code, inst=None):
		return next(r for r in (inst or self.inst).stages if r.stage_code == code)

	def fresh(self):
		return frappe.get_doc("Solar Installation", self.inst.name)

	def financed(self):
		self.inst.db_set("is_financed", 1)
		self.inst = self.fresh()

	def test_form1_starts_with_the_order_when_the_customer_pays(self):
		self.assertEqual(self.row("FRM1").status, "Pending")
		tasks._start_form1_early(self.inst, "ORD")
		inst = self.fresh()
		self.assertEqual((self.row("FRM1", inst).status, str(self.row("FRM1", inst).actual_start_date)), ("In Progress", today()))
		self.assertEqual(self.row("F1PAY", inst).status, "Pending")

	def test_a_bank_loan_jobs_form1_waits_for_the_advance(self):
		self.financed()
		tasks._start_form1_early(self.inst, "ORD")
		self.assertEqual(self.row("FRM1", self.fresh()).status, "Pending")

	def test_the_plan_lays_form1_from_the_start_only_when_the_customer_pays(self):
		advance = add_days(today(), 10)
		self.inst.advance_received_on = advance
		stages.plan_dates(self.inst)
		start = getdate(self.inst.get("execution_start_date") or self.inst.order_date)
		self.assertEqual(str(self.row("FRM1").planned_start_date), str(start))
		self.assertEqual(str(self.row("F1PAY").planned_start_date), advance)
		self.inst.is_financed = 1
		stages.plan_dates(self.inst)
		self.assertEqual(str(self.row("FRM1").planned_start_date), advance)

	def test_the_customer_is_asked_once_form1_is_submitted(self):
		state = payment_followup.state(self.inst, "ADV")
		self.assertTrue(state["waiting"])
		self.assertFalse(state["due_on"])
		payment_followup.on_form1_completed(self.inst, "FRM1")
		self.assertEqual(str(self.fresh().advance_followup_due_on), today())

	def test_the_bank_is_asked_days_after_the_sanction_until_the_first_ask(self):
		self.financed()
		payment_followup.on_form1_completed(self.inst, "FRM1")
		self.assertFalse(self.fresh().advance_followup_due_on)
		sanctioned = add_days(today(), -2)
		loan = frappe._dict(solar_installation=self.inst.name, sanctioned_on=sanctioned)
		payment_followup.on_loan_sanctioned(loan)
		self.assertEqual(str(self.fresh().advance_followup_due_on), add_days(sanctioned, 5))
		# A corrected sanction date moves it - until the bank has been asked.
		loan.sanctioned_on = today()
		payment_followup.on_loan_sanctioned(loan)
		self.assertEqual(str(self.fresh().advance_followup_due_on), add_days(today(), 5))

	def test_an_ask_is_logged_and_the_next_falls_due_later(self):
		self.inst.db_set("advance_followup_due_on", today())
		self.assertEqual(payment_followup.daily_chase(), 1)
		self.assertEqual(payment_followup.daily_chase(), 0)
		self.assertEqual(len(payment_followup._todos(self.fresh())), 1)
		payment_followup.log_ask(self.inst.name, "WhatsApp", note="Will pay Monday")
		inst = self.fresh()
		self.assertEqual(str(inst.advance_followup_due_on), add_days(today(), 3))
		ask = inst.payment_followups[-1]
		self.assertEqual((ask.task_code, ask.payer, ask.via, ask.note), ("ADV", "Client", "WhatsApp", "Will pay Monday"))
		self.assertFalse(payment_followup._todos(inst))
		with self.assertRaises(frappe.ValidationError):
			payment_followup.log_ask(self.inst.name, "Pigeon")
		with self.assertRaises(frappe.ValidationError):
			payment_followup.log_ask(self.inst.name, "Call", next_on=add_days(today(), -1))

	def test_nothing_is_asked_once_the_advance_is_covered(self):
		self.inst.db_set("advance_followup_due_on", today())
		payment_followup.daily_chase()
		inst = self.fresh()
		with patch.object(payment_followup, "outstanding", return_value=0):
			payment_followup.after_payment(inst)
			self.assertIsNone(inst.advance_followup_due_on)
			self.assertFalse(payment_followup._todos(inst))
			self.assertFalse(payment_followup.state(inst, "ADV")["can_ask"])
			with self.assertRaises(frappe.ValidationError):
				payment_followup.log_ask(self.inst.name, "Call")

	def test_a_payment_sent_back_is_asked_for_again(self):
		row = self.row("FRM1")
		row.status = "Completed"
		payment_followup.after_send_back(self.inst)
		self.assertEqual(str(self.inst.advance_followup_due_on), today())

	def test_the_bank_is_written_to_about_its_sanction(self):
		self.financed()
		loan = frappe._dict(name="LOAN-T", status="Sanctioned", lender="SBI", lender_branch="Aluva",
			relationship_manager="Mr Nair", contact_number="9876543210", loan_sanction_no="SAN/42", sanctioned_on=today())
		with patch.object(payment_followup, "_loan", return_value=loan):
			message = payment_followup.ask_message(self.inst.name)
			state = payment_followup.state(self.inst, "ADV")
		self.assertIn("SAN/42", message["message"])
		self.assertIn("₹", message["message"])
		self.assertTrue(message["whatsapp"].startswith("https://wa.me/919876543210?text="))
		self.assertEqual((state["payer"], state["name"], state["person"]), ("Bank", "SBI, Aluva", "Mr Nair"))
