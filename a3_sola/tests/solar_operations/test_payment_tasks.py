# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The advance is confirmed, not documented: received with its receipt, then Accounts confirms."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import documents, payment_tasks, tasks
from a3_sola.tests.solar_operations.fixtures import make_installation

ADV = "ADV"
PAID = {"amount": 25000, "bank": "SBI Aluva", "company": "Renewcore"}


def ensure_firms(company):
	"""The company's receiving firms, each with a ledger, as the patch sets them up."""
	if payment_tasks.firms(company):
		return
	from a3_sola.patches.v1_2.payment_receiving_firms import FIRMS, _ledger

	name = frappe.db.get_value("Solar Company Account Mapping", {"company": company}, "name")
	mapping = frappe.get_doc("Solar Company Account Mapping", name) if name else frappe.get_doc(
		{"doctype": "Solar Company Account Mapping", "company": company})
	parent = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name")
	for firm in FIRMS:
		mapping.append("receiving_firms", {"firm_name": firm, "account": _ledger(company, parent, f"{firm} Receipts")})
	mapping.flags.ignore_permissions = True
	mapping.save()


def file_receipt(installation):
	inst = frappe.get_doc("Solar Installation", installation)
	f = frappe.get_doc({"doctype": "File", "file_name": "advance.txt", "content": b"advance", "is_private": 1,
		"attached_to_doctype": "Solar Installation", "attached_to_name": installation}).insert(ignore_permissions=True)
	documents.register_document(inst, ADV, "Solar Installation", installation, payment_tasks.PAYMENT_TASKS[ADV],
		f.file_url, kind="Uploaded")


class TestAdvancePayment(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation().name
		ensure_firms(frappe.db.get_value("Solar Installation", self.job, "company"))
		if not any(r.stage_code == ADV for r in frappe.get_doc("Solar Installation", self.job).stages):
			self.skipTest("no advance task on this site's template")

	def tearDown(self):
		frappe.set_user("Administrator")

	def row(self):
		return next(r for r in frappe.get_doc("Solar Installation", self.job).stages if r.stage_code == ADV)

	def test_it_opens_its_own_page_not_a_document(self):
		target = tasks.open_task(self.job, ADV, create_draft=0)
		self.assertIsNone(target["doctype"])
		self.assertTrue(target["url"].endswith("/tasks/ADV"))

	def test_received_needs_the_receipt(self):
		if payment_tasks.state(self.job, ADV)["document"]["file_url"]:
			self.skipTest("the job already has a receipt")
		with self.assertRaises(frappe.ValidationError):
			payment_tasks.mark_received(self.job, ADV, **PAID)

	def test_received_goes_to_accounts_who_complete_it(self):
		file_receipt(self.job)
		state = payment_tasks.mark_received(self.job, ADV, **PAID)
		self.assertEqual(state["task"]["status"], payment_tasks.AWAITING)
		self.assertNotEqual(self.row().status, "Completed")
		state = payment_tasks.confirm(self.job, ADV)
		self.assertEqual(state["task"]["status"], "Completed")
		self.assertEqual(self.row().completed_by, "Administrator")

	def test_accounts_can_send_it_back(self):
		file_receipt(self.job)
		payment_tasks.mark_received(self.job, ADV, **PAID)
		state = payment_tasks.send_back(self.job, ADV, "Not in the bank statement")
		self.assertEqual(state["task"]["status"], "Pending")
		self.assertIn("Not in the bank statement", state["remarks"])
		self.assertFalse(self.row().payment_received_by)

	def test_only_accounts_confirm(self):
		file_receipt(self.job)
		payment_tasks.mark_received(self.job, ADV, **PAID)
		user = frappe.get_doc({"doctype": "User", "email": f"seller{frappe.generate_hash(length=5)}@example.com",
			"first_name": "Seller", "send_welcome_email": 0, "roles": [{"role": "Solar Sales Executive"}]}).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			payment_tasks.confirm(self.job, ADV)

	def test_the_amount_bank_and_company_are_asked_for_and_kept(self):
		file_receipt(self.job)
		with self.assertRaises(frappe.ValidationError):
			payment_tasks.mark_received(self.job, ADV, amount=25000, bank="", company="Renewcore")
		with self.assertRaises(frappe.ValidationError):
			payment_tasks.mark_received(self.job, ADV, amount=25000, bank="SBI", company="Somebody Else")
		state = payment_tasks.mark_received(self.job, ADV, **PAID)
		self.assertEqual((state["payment"]["amount"], state["payment"]["bank"], state["payment"]["company"]),
			(25000, "SBI Aluva", "Renewcore"))
		# The firm's mapped ledger goes with it.
		self.assertEqual(state["payment"]["account"], payment_tasks.firms(
			frappe.db.get_value("Solar Installation", self.job, "company"))["Renewcore"])
		payment_tasks.confirm(self.job, ADV)
		from a3_sola.api import billing

		ledger = billing.customer_statement(frappe.get_doc("Solar Installation", self.job))
		rows = ledger["rows"] if isinstance(ledger, dict) else ledger
		self.assertTrue(any(r["credit"] == 25000 and "Renewcore" in r["particulars"] for r in rows))


class TestPackagePaymentTerms(FrappeTestCase):
	"""A package names its payment terms; the advance is checked against them."""

	def test_the_advance_due_follows_the_packages_terms(self):
		from a3_sola.api import billing

		job = make_installation()
		terms = frappe.get_all("Billing Milestone Template", filters={"company": job.company, "is_active": 1},
			fields=["name", "applicable_funding"])
		own = next((t.name for t in terms if t.applicable_funding != "Financed"), None)
		financed = next((t.name for t in terms if t.applicable_funding == "Financed"), None)
		if not (own and financed and job.solar_package):
			self.skipTest("no payment terms or package on this site")
		frappe.db.set_value("Solar Package", job.solar_package, {"payment_terms": own, "financed_payment_terms": financed})
		job.db_set({"is_financed": 0, "gross_contract_value": 200000})
		due = billing.advance_due(job.name)
		self.assertEqual(due["terms"], own)
		advance = sum(frappe.get_all("Billing Milestone Template Detail",
			filters={"parent": own, "is_advance": 1}, pluck="percentage"))
		self.assertEqual(due["amount"], 200000 * advance / 100)
		job.db_set("is_financed", 1)
		self.assertEqual(billing.advance_due(job.name)["terms"], financed)


class TestPaymentPhases(FrappeTestCase):
	"""The customer pays in the phases of the terms; a shortfall is asked for again next time."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation().name
		ensure_firms(frappe.db.get_value("Solar Installation", self.job, "company"))
		from a3_sola.api import billing

		self.schedule = billing.payment_phases(self.job)
		if not self.schedule or len(self.schedule["phases"]) < 2:
			self.skipTest("no phased payment terms for this job")

	def receipt(self, code):
		inst = frappe.get_doc("Solar Installation", self.job)
		f = frappe.get_doc({"doctype": "File", "file_name": f"{code}.txt", "content": b"paid", "is_private": 1,
			"attached_to_doctype": "Solar Installation", "attached_to_name": self.job}).insert(ignore_permissions=True)
		documents.register_document(inst, code, "Solar Installation", self.job, payment_tasks.PAYMENT_TASKS[code],
			f.file_url, kind="Uploaded")

	def test_a_short_advance_is_carried_into_the_next_payment(self):
		advance = self.schedule["phases"][0]
		self.receipt("ADV")
		payment_tasks.mark_received(self.job, "ADV", amount=advance["amount"] - 1000, bank="SBI", company="Renewcore")
		payment_tasks.confirm(self.job, "ADV")
		nxt = self.schedule["phases"][1]
		due = payment_tasks.state(self.job, nxt["code"])["due"]
		self.assertEqual(due["arrears"], 1000)
		self.assertEqual(due["collect"], nxt["amount"] + 1000)

	def test_a_payment_confirmed_without_an_amount_counts_in_full(self):
		"""Advances confirmed before amounts were recorded: the phase was paid, only the rest is asked."""
		advance, nxt = self.schedule["phases"][:2]
		frappe.db.set_value("Installation Stage Log", {"parent": self.job, "stage_code": "ADV"},
			{"status": "Completed", "payment_amount": 0})
		due = payment_tasks.state(self.job, nxt["code"])["due"]
		first = due["schedule"][0]
		self.assertEqual((first["received"], first["remaining"], first["assumed"]), (advance["amount"], 0, True))
		self.assertEqual((due["arrears"], due["collect"]), (0, nxt["amount"]))
		self.assertEqual(due["remaining_total"], due["base"] - advance["amount"])

	def test_paying_ahead_lowers_the_next_payment(self):
		advance, nxt = self.schedule["phases"][:2]
		self.receipt("ADV")
		payment_tasks.mark_received(self.job, "ADV", amount=advance["amount"] + 500, bank="SBI", company="Renewcore")
		payment_tasks.confirm(self.job, "ADV")
		due = payment_tasks.state(self.job, nxt["code"])["due"]
		self.assertEqual((due["arrears"], due["credit"], due["collect"]), (0, 500, nxt["amount"] - 500))

	def test_every_payment_task_has_its_page(self):
		for phase in self.schedule["phases"]:
			self.assertTrue(tasks.open_task(self.job, phase["code"], create_draft=0)["url"].endswith("/tasks/" + phase["code"]))

	def test_no_third_payment_on_two_phase_terms(self):
		inst = frappe.get_doc("Solar Installation", self.job)
		with patch.object(billing_module(), "payment_phases",
				return_value={"terms": "T", "base": 100, "phases": [{"code": "ADV"}, {"code": "BAL"}]}):
			payment_tasks.apply_phases(inst)
		row = next(r for r in inst.stages if r.stage_code == "PCOM")
		self.assertEqual((row.status, row.skip_reason), ("Skipped", payment_tasks.NOT_IN_TERMS))


def billing_module():
	from a3_sola.api import billing

	return billing
