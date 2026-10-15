# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Paid out of pocket for a task, claimed back: raised by the person on the task, approved
by an operations manager, paid by Accounts - each step held to its role, and what was
claimed fixed once it is decided."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.solar_operations.doctype.expense_reimbursement import expense_reimbursement as er
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestReimbursements(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def claim(self, amount=350):
		return er.raise_claim(self.installation.name, "STMP", amount, "Courier to KSEB")

	def test_the_stamp_form_raises_a_claim_when_it_was_paid_from_pocket(self):
		from a3_sola.api import portal_crud

		made = portal_crud.create_record(
			slug="agreements", source_dt="Solar Installation", source=self.installation.name, source_task="STMP",
			stamp_paper_status="1", stamp_paper_value="200", claim_reimbursement="1", stamp_paper_remarks="Bought at Aluva",
		)
		agreement = frappe.get_doc("Solar Agreement", made["name"])
		self.assertTrue(agreement.reimbursement, "no reimbursement raised")
		claim = frappe.get_doc("Expense Reimbursement", agreement.reimbursement)
		self.assertEqual((claim.status, claim.amount, claim.task_code), ("Pending Approval", 200, "STMP"))
		self.assertEqual((claim.source_doctype, claim.source_document), ("Solar Agreement", agreement.name))
		self.assertEqual(claim.claimant, frappe.session.user)

	def test_not_bought_raises_nothing(self):
		from a3_sola.api import portal_crud

		made = portal_crud.create_record(
			slug="agreements", source_dt="Solar Installation", source=self.installation.name, source_task="STMP",
			stamp_paper_status="0", claim_reimbursement="1",
		)
		self.assertFalse(frappe.db.get_value("Solar Agreement", made["name"], "reimbursement"))

	def test_approved_then_paid(self):
		claim = self.claim()
		er.approve(claim.name, "OK")
		self.assertEqual(frappe.db.get_value("Expense Reimbursement", claim.name, "status"), "Approved")
		with self.assertRaises(frappe.ValidationError):
			er.mark_paid(claim.name, today(), "Barter")
		er.mark_paid(claim.name, today(), "UPI", "UTR123")
		claim.reload()
		self.assertEqual((claim.status, claim.payment_mode, claim.payment_reference), ("Paid", "UPI", "UTR123"))
		self.assertEqual(claim.paid_by, frappe.session.user)

	def test_a_rejection_says_why(self):
		claim = self.claim()
		with self.assertRaises(frappe.ValidationError):
			er.reject(claim.name, " ")
		er.reject(claim.name, "No receipt")
		claim.reload()
		self.assertEqual((claim.status, claim.approval_remarks), ("Rejected", "No receipt"))

	def test_each_step_is_its_roles(self):
		claim = self.claim()
		with patch.object(frappe, "get_roles", return_value=["Solar Operations Executive"]):
			with self.assertRaises(frappe.PermissionError):
				er.approve(claim.name)
		er.approve(claim.name)
		with patch.object(frappe, "get_roles", return_value=["Solar Operations Manager"]):
			with self.assertRaises(frappe.PermissionError):
				er.mark_paid(claim.name, today(), "Cash")

	def test_a_decided_claim_cannot_be_changed(self):
		claim = self.claim()
		claim.amount = 400
		claim.save()  # still waiting: a correction is fine
		er.approve(claim.name)
		claim.reload()
		claim.amount = 900
		with self.assertRaises(frappe.ValidationError):
			claim.save()

	def test_a_claim_is_raised_from_inside_a_task(self):
		from a3_sola.api import portal_tasks, reimbursements

		with patch.object(frappe, "request", None):
			made = reimbursements.raise_claim(self.installation.name, "ADV", amount="120", expense_date=today())
		claim = frappe.get_doc("Expense Reimbursement", made["name"])
		self.assertEqual((claim.task_code, claim.amount, claim.status), ("ADV", 120, "Pending Approval"))
		self.assertTrue(claim.description)  # the task's name when nothing is said
		panel = portal_tasks.task_documents(self.installation.name, "ADV")
		self.assertIn(claim.name, [c["name"] for c in panel["claims"]])

	def allow(self, code, on=1):
		template = frappe.db.get_value("Solar Installation", self.installation.name, "stage_template")
		frappe.db.sql("""update `tabInstallation Stage Template Detail` set allow_reimbursement = %s
			where parent = %s and stage_code = %s""", (on, template, code))

	def test_only_the_tasks_the_template_ticks_offer_a_claim(self):
		from a3_sola.www.a3solaportal.collections import task_claim

		self.allow("ADV", 0)
		self.assertIsNone(task_claim(self.installation.name, "ADV"))
		self.assertTrue(task_claim(self.installation.name, "STMP"), "the stamp paper is ticked")
		claim = self.claim()  # raised before: still there to view
		self.allow("STMP", 0)
		self.assertEqual(task_claim(self.installation.name, "STMP")["existing"]["name"], claim.name)
		self.allow("STMP", 1)

	def test_task_pages_carry_the_claim_button_the_stamp_form_its_own_box(self):
		from a3_sola.www.a3solaportal.collections import CLAIM_IN_FORM, task_claim

		self.allow("ADV", 1)
		claim = task_claim(self.installation.name, "ADV")
		self.assertEqual((claim["task"], claim["installation"]), ("ADV", self.installation.name))
		self.assertTrue(claim["task_name"])
		self.assertIsNone(task_claim(self.installation.name, "NOPE"))
		self.assertIn("STMP", CLAIM_IN_FORM)
		self.allow("ADV", 0)

	def test_a_raised_claim_is_viewed_not_claimed_again(self):
		from a3_sola.www.a3solaportal.collections import task_claim

		self.assertIsNone(task_claim(self.installation.name, "STMP")["existing"])
		claim = self.claim()
		self.assertEqual(task_claim(self.installation.name, "STMP")["existing"]["name"], claim.name)
		er.reject(claim.name, "Duplicate")
		self.assertIsNone(task_claim(self.installation.name, "STMP")["existing"], "a rejected claim can be raised again")
