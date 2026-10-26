# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The job's payment schedule lives on its billing plan: each milestone knows its payment task,
a payment is recorded with its receipt and counts once Accounts confirms it, a phase can be
paid in parts - its task done only when nothing is pending - and the job page shows it all."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from a3_sola.api import billing, payment_tasks
from a3_sola.patches.v1_2 import payment_schedule_on_plan
from a3_sola.tests.solar_operations.test_payment_tasks import ensure_firms
from a3_sola.tests.solar_operations.test_portal_tasks import posted
from a3_sola.tests.solar_projects.fixtures import installation_with_customer

PAID = {"bank": "SBI Aluva", "company": "Renewcore", "mode": "Bank Transfer"}


class TestPaymentSchedule(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.inst = installation_with_customer()
		ensure_firms(self.inst.company)
		self.assertTrue(billing.ensure_plan_for_installation(self.inst.name, replay=False))

	def plan(self):
		return billing.plan_of(self.inst.name)

	def milestone(self, code):
		return next(m for m in self.plan().milestones if m.phase_code == code)

	def task(self, code):
		return next(r for r in frappe.get_doc("Solar Installation", self.inst.name).stages if r.stage_code == code)

	def pay(self, amount, code="ADV", reference="UTR1"):
		with patch.object(frappe, "request", posted(f"{code}-{reference}.txt", f"{code} {amount} {reference}".encode())):
			return payment_tasks.mark_received(self.inst.name, code, amount=amount, reference=reference, **PAID)

	def payment(self, reference):
		return next(p for p in self.plan().payments if p.reference_no == reference)

	def test_each_milestone_knows_its_payment_task(self):
		plan = self.plan()
		self.assertEqual([m.phase_code for m in plan.milestones], ["ADV", "BAL", "PCOM"])
		self.assertEqual([m.payment_status for m in plan.milestones], ["Unpaid"] * 3)
		self.assertEqual(flt(plan.total_pending), flt(plan.gross_contract_value))

	def test_a_recorded_payment_waits_for_accounts(self):
		state = self.pay(50000)
		self.assertEqual(state["task"]["status"], payment_tasks.AWAITING)
		p = self.payment("UTR1")
		self.assertEqual((p.status, p.payment_mode, flt(p.amount)), ("Awaiting Confirmation", "Bank Transfer", 50000))
		self.assertTrue(p.receipt)
		self.assertEqual(self.milestone("ADV").payment_status, "Unpaid")
		self.assertEqual(flt(self.plan().total_received), 0)

	def test_a_phase_paid_in_parts_is_done_when_nothing_is_pending(self):
		advance = flt(self.milestone("ADV").milestone_amount)
		self.pay(100000, reference="UTR1")
		state = payment_tasks.confirm(self.inst.name, "ADV")
		self.assertEqual(self.milestone("ADV").payment_status, "Partly Paid")
		self.assertEqual(flt(self.milestone("ADV").pending_amount), flt(advance - 100000, 2))
		self.assertEqual(state["task"]["status"], "In Progress")
		self.assertEqual(state["payment_status"], "Partly Paid")
		self.pay(advance - 100000, reference="UTR2")
		state = payment_tasks.confirm(self.inst.name, "ADV", payment=self.payment("UTR2").name)
		self.assertEqual(self.milestone("ADV").payment_status, "Paid")
		self.assertEqual(state["task"]["status"], "Completed")
		self.assertEqual(len(self.plan().payments), 2)

	def test_a_payment_sent_back_does_not_count(self):
		self.pay(50000)
		state = payment_tasks.send_back(self.inst.name, "ADV", "Not in the bank statement", payment=self.payment("UTR1").name)
		self.assertEqual(self.payment("UTR1").status, "Sent Back")
		self.assertEqual(flt(self.plan().total_received), 0)
		self.assertEqual(state["task"]["status"], "Pending")

	def test_paying_ahead_pays_the_next_milestone(self):
		advance = flt(self.milestone("ADV").milestone_amount)
		self.pay(advance + 9500)
		payment_tasks.confirm(self.inst.name, "ADV")
		self.assertEqual(self.milestone("ADV").payment_status, "Paid")
		self.assertEqual(self.milestone("BAL").payment_status, "Partly Paid")
		self.assertEqual(flt(self.milestone("BAL").received_amount), 9500)

	def test_a_milestone_falls_due_its_credit_days_after_it_triggers(self):
		billing.on_stage_completed(self.inst.name, "IWOI")
		row = self.milestone("BAL")
		self.assertTrue(row.is_triggered)
		self.assertEqual(str(row.due_date), str(add_days(today(), int(row.credit_days or 0))))

	def test_the_job_page_shows_the_schedule(self):
		self.pay(50000)
		s = billing.schedule(frappe.get_doc("Solar Installation", self.inst.name))
		self.assertEqual(len(s["milestones"]), 3)
		self.assertEqual(s["payments"][0]["status"], "Awaiting Confirmation")
		self.assertTrue(s["awaiting_text"])
		self.assertIn("ADV", [p["code"] for p in s["phases"]])
		self.assertTrue(s["can_record"] and s["can_confirm"])
		self.assertIn("Renewcore", s["firms"])

	def test_the_patch_moves_a_payment_kept_on_the_task(self):
		advance = flt(self.milestone("ADV").milestone_amount)
		inst = frappe.get_doc("Solar Installation", self.inst.name)
		row = next(r for r in inst.stages if r.stage_code == "ADV")
		frappe.db.set_value(row.doctype, row.name, {"payment_amount": advance, "payment_bank": "SBI", "status": "Completed",
			"actual_completion_date": today()})
		plan = self.plan()
		for m in plan.milestones:
			m.phase_code = None
		payment_schedule_on_plan.phases(plan)
		payment_schedule_on_plan.payments(plan, frappe.get_doc("Solar Installation", self.inst.name))
		billing.recompute_summary(plan)
		self.assertEqual([m.phase_code for m in plan.milestones], ["ADV", "BAL", "PCOM"])
		moved = next(p for p in plan.payments if p.phase_code == "ADV")
		self.assertEqual((moved.status, flt(moved.amount)), ("Confirmed", advance))
		self.assertEqual(plan.milestones[0].payment_status, "Paid")

	def test_a_job_without_a_plan_keeps_its_one_payment_on_the_task(self):
		inst = installation_with_customer(gross_contract_value=0)
		self.assertIsNone(billing.plan_of(inst.name))
		self.assertIsNone(billing.schedule(inst))


class TestPaymentStatement(FrappeTestCase):
	"""What the customer owes, has paid and still has to pay, as the team's letter lays it
	out - the same on each payment task, signed and sealed or not."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.inst = installation_with_customer()
		ensure_firms(self.inst.company)
		billing.ensure_plan_for_installation(self.inst.name, replay=False)

	def job(self):
		return frappe.get_doc("Solar Installation", self.inst.name)

	def confirmed(self, amount, reference):
		with patch.object(frappe, "request", posted(f"ADV-{reference}.txt", f"ADV {amount} {reference}".encode())):
			payment_tasks.mark_received(self.inst.name, "ADV", amount=amount, reference=reference, **PAID)
		payment_tasks.confirm(self.inst.name, "ADV")

	def test_the_balance_is_the_cost_less_what_was_received_and_the_discount(self):
		from a3_sola.api import payment_statement_print as statement

		self.confirmed(100000, "UTR1")
		plan = billing.plan_of(self.inst.name)
		plan.special_discount = 5000
		plan.flags.ignore_validate_update_after_submit = True
		plan.save(ignore_permissions=True)
		f = statement.context(self.job())
		labels = [l["label"] for l in f.lines]
		self.assertEqual(labels[0], "Total Project Cost Including Structure")
		payment = next(l for l in f.lines if l["label"].startswith("Payment received"))
		self.assertEqual(payment["label"], "Payment received (Bank)")
		self.assertEqual(payment["date"], frappe.utils.formatdate(today(), "dd/MM/yyyy"))
		self.assertIn("Special Discount", labels)
		cost = next(l["amount"] for l in f.lines if l["label"].startswith("Total cost"))
		self.assertEqual(f.lines[-1]["label"], "Balance Payable")
		self.assertEqual(f.lines[-1]["amount"], flt(cost - 100000 - 5000, 2))
		self.assertEqual(f.lines[-1]["text"], statement.amount_text(cost - 105000))
		# the discount comes off the last milestone, and the schedule's pending
		self.assertEqual(flt(billing.plan_of(self.inst.name).total_pending),
			flt(flt(plan.gross_contract_value) - 105000, 2))

	def test_each_payment_task_offers_it_to_sign_and_seal(self):
		from a3_sola.api import payment_statement_print as statement, portal_tasks

		for code in statement.TASKS:
			links = portal_tasks._prints(frappe._dict(stage_code=code), self.inst.name)[statement.CODE]
			self.assertEqual([p["label"] for p in links], ["View Payment Statement", "Download Payment Statement"])
			self.assertTrue(all(p["signable"] for p in links))
		name, pdf = statement.render(self.inst.name, signed=False)
		self.assertTrue(name.endswith("(unsigned).pdf"))
		self.assertTrue(pdf.startswith(b"%PDF"))

	def test_the_patch_lists_it_on_the_payment_tasks(self):
		from a3_sola.patches.v1_2 import payment_statement_rows

		inst = self.job()
		inst.set("documents", [d for d in inst.documents if d.document_name != payment_statement_rows.NAME])
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		payment_statement_rows.execute()
		inst = self.job()
		codes = {r.stage_code for r in inst.stages if r.status != "Skipped"} & set(payment_statement_rows.TASKS)
		self.assertEqual({d.stage_code for d in inst.documents if d.document_name == payment_statement_rows.NAME}, codes)


class TestReceiptPerPayment(FrappeTestCase):
	"""A phase paid in parts takes a receipt per payment: after the first, the page offers a
	fresh numbered receipt to upload for the next."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.inst = installation_with_customer()
		ensure_firms(self.inst.company)
		self.assertTrue(billing.ensure_plan_for_installation(self.inst.name, replay=False))

	def test_the_second_payment_gets_its_own_receipt(self):
		from a3_sola.api import portal_tasks

		with patch.object(frappe, "request", posted("ADV-1.txt", b"first receipt")):
			payment_tasks.mark_received(self.inst.name, "ADV", amount=50000, reference="UTR1", **PAID)
		doc = payment_tasks.state(self.inst.name, "ADV")["document"]
		self.assertIsNone(doc["file_url"], "the first receipt is the first payment's")
		self.assertTrue(doc["name"].endswith("(2)"))
		# The page uploads into that numbered row, then records the payment against it.
		with patch.object(frappe, "request", posted("ADV-2.txt", b"second receipt")):
			portal_tasks.upload(self.inst.name, "ADV", document_name=doc["name"])
		doc = payment_tasks.state(self.inst.name, "ADV")["document"]
		self.assertTrue(doc["file_url"])
		with patch.object(frappe, "request", None):
			payment_tasks.mark_received(self.inst.name, "ADV", amount=30000, reference="UTR2", **PAID)
		receipts = [p.receipt for p in billing.plan_of(self.inst.name).payments]
		self.assertEqual(len(set(receipts)), 2)
