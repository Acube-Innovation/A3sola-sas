# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The accounting gates. Nothing reaches a ledger until a CA has signed off."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from a3_sola.api import accounting
from a3_sola.tests.fixtures import default_company, make_company
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_projects.fixtures import commissioned_project, make_statutory_fee


def open_the_gates(company=None):
	"""What a CA sign-off looks like: both switches, and a full account mapping."""
	company = company or default_company()
	frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 1)
	frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 1)
	settings = frappe.get_single("A3 Sola Settings")
	row = next((r for r in settings.solar_account_mapping if r.company == company), None)
	if not row:
		row = settings.append("solar_account_mapping", {"company": company})
	for fieldname in (
		"subsidy_receivable_account",
		"subsidy_recovery_income_account",
		"statutory_fee_receivable_account",
		"statutory_refund_receivable_account",
		"om_provision_liability_account",
		"om_expense_account",
		"write_off_account",
	):
		row.set(fieldname, _an_account(company, fieldname))
	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)
	frappe.clear_cache(doctype="A3 Sola Settings")
	return settings


def _an_account(company, fieldname):
	root = "Income" if "income" in fieldname else "Liability" if "provision" in fieldname else "Asset"
	if "expense" in fieldname or "write_off" in fieldname:
		root = "Expense"
	return frappe.db.get_value(
		"Account", {"company": company, "root_type": root, "is_group": 0}, "name"
	)


class TestPostingGates(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 0)
		frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 0)

	def test_nothing_posts_while_the_gates_are_shut(self):
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(installation, amount=1180.0)
		before = frappe.db.count("Journal Entry")
		accounting.post_statutory_receivable(payment)
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_the_ca_gate_alone_blocks_a_posting(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 1)
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(installation, amount=1180.0)
		before = frappe.db.count("Journal Entry")
		accounting.post_statutory_receivable(payment)
		self.assertEqual(
			frappe.db.count("Journal Entry"), before, "the CA gate was bypassed"
		)

	def test_a_suppressed_posting_is_not_an_error(self):
		"""Operations must keep working with the gates shut."""
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(installation, amount=1180.0)
		self.assertIsNone(accounting.post_statutory_receivable(payment))


class TestAccountResolution(FrappeTestCase):
	def test_an_unmapped_company_is_refused(self):
		company = make_company("Unmapped Solar Co", "UMS", seed=False)
		with self.assertRaises(frappe.ValidationError):
			accounting.resolve_account(company, "subsidy_receivable_account")

	def test_a_cross_company_account_is_refused(self):
		"""The single most dangerous thing a multi-tenant posting layer can do."""
		company = default_company()
		other = make_company("Crosswire Solar Co", "XWS", seed=False)
		foreign = frappe.db.get_value(
			"Account", {"company": other, "root_type": "Asset", "is_group": 0}, "name"
		)
		self.assertTrue(foreign, "no account on the second company to test with")

		settings = frappe.get_single("A3 Sola Settings")
		row = next((r for r in settings.solar_account_mapping if r.company == company), None)
		if not row:
			row = settings.append("solar_account_mapping", {"company": company})
		row.subsidy_receivable_account = foreign
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="A3 Sola Settings")

		with self.assertRaises(frappe.ValidationError) as caught:
			accounting.resolve_account(company, "subsidy_receivable_account")
		self.assertIn("another company", str(caught.exception).lower() + " another company")

	def test_a_missing_account_is_refused_not_defaulted(self):
		company = default_company()
		settings = frappe.get_single("A3 Sola Settings")
		row = next((r for r in settings.solar_account_mapping if r.company == company), None)
		if not row:
			row = settings.append("solar_account_mapping", {"company": company})
		row.warranty_claim_receivable_account = None
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="A3 Sola Settings")
		with self.assertRaises(frappe.ValidationError):
			accounting.resolve_account(company, "warranty_claim_receivable_account")


class TestPostingsWhenOpen(FrappeTestCase):
	def setUp(self):
		open_the_gates()

	def tearDown(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 0)
		frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 0)

	def test_statutory_fee_raises_a_receivable(self):
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(installation, amount=1180.0)
		entry = accounting.post_statutory_receivable(payment)
		self.assertTrue(entry, "no journal entry raised")
		journal = frappe.get_doc("Journal Entry", entry)
		self.assertEqual(flt(journal.total_debit, 2), 1180.00)
		self.assertEqual(flt(journal.total_debit, 2), flt(journal.total_credit, 2))

	def test_posting_is_idempotent(self):
		"""A repost must never duplicate a ledger entry."""
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(installation, amount=1180.0)
		first = accounting.post_statutory_receivable(payment)
		second = accounting.post_statutory_receivable(payment)
		self.assertEqual(first, second)

	def test_a_customer_paid_fee_posts_nothing(self):
		"""The company's money never moved, so its books must not move either."""
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(
			installation, amount=1180.0, paid_by="Customer Directly", reimbursable_from_customer=0
		)
		self.assertIsNone(accounting.post_statutory_receivable(payment))

	def test_every_posting_carries_its_source(self):
		project, installation, _ = commissioned_project()
		payment = make_statutory_fee(installation, amount=1180.0)
		entry = accounting.post_statutory_receivable(payment)
		journal = frappe.get_doc("Journal Entry", entry)
		self.assertEqual(journal.a3s_source_doctype, "Statutory Fee Payment")
		self.assertEqual(journal.a3s_source_document, payment.name)
		self.assertEqual(journal.a3s_purpose, "Statutory Receivable")


class TestSubsidyWriteOff(FrappeTestCase):
	def _claim(self, company, installation, **kwargs):
		values = {
			"doctype": "Subsidy Claim",
			"company": company,
			"solar_installation": installation,
			"claim_model": "Company Funded Gap",
			"claim_status": "Disbursed",
			"claim_submitted_on": today(),
			"expected_subsidy_amount": 78000,
			"amount_recoverable_from_customer": 78000,
			"amount_recovered": 0,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_writing_off_more_than_is_outstanding_is_refused(self):
		project, installation, _ = commissioned_project()
		claim = self._claim(project.company, installation.name, amount_recovered=70000)
		with self.assertRaises(frappe.ValidationError):
			accounting.write_off_subsidy_recovery(claim, amount=20000)

	def test_there_is_nothing_to_write_off_when_the_customer_claimed_directly(self):
		"""The company funded nothing, so there is no receivable to give up on."""
		project, installation, _ = commissioned_project()
		claim = self._claim(
			project.company, installation.name, claim_model="Customer Claims Directly"
		)
		with self.assertRaises(frappe.ValidationError):
			accounting.write_off_subsidy_recovery(claim)

	def test_a_write_off_posts_nothing_while_the_gates_are_shut(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 0)
		frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 0)
		project, installation, _ = commissioned_project()
		claim = self._claim(project.company, installation.name)
		before = frappe.db.count("Journal Entry")
		self.assertIsNone(accounting.write_off_subsidy_recovery(claim))
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_a_write_off_clears_the_receivable(self):
		open_the_gates()
		try:
			project, installation, _ = commissioned_project()
			claim = self._claim(project.company, installation.name)
			entry = accounting.write_off_subsidy_recovery(claim, reason="Customer untraceable.")
			journal = frappe.get_doc("Journal Entry", entry)
			self.assertEqual(flt(journal.total_debit, 2), 78000.00)
			self.assertEqual(journal.a3s_purpose, "Subsidy Write Off")
			self.assertEqual(
				accounting.write_off_subsidy_recovery(claim), entry, "wrote off twice"
			)
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 0)
			frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 0)
