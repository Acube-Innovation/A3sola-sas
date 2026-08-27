# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Snags, subsidy claims and statutory fees.

The Operations module posts NOTHING. Phase 3 owns the ledger through the extension points.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.api import stages
from a3_sola.tests.solar_operations.fixtures import (
	attach_stage_documents,
	capture_serials,
	complete_through,
	make_installation,
)

CHAIN_TO_PCR = [
	"ORD", "NPA", "FEAS", "DSGN", "PROC", "DISP", "INST", "KREG", "NMTR", "KTST", "AGMT", "COMM",
]


def make_snag(installation, severity="Major", **kwargs):
	values = {
		"doctype": "Installation Snag",
		"company": installation.company,
		"solar_installation": installation.name,
		"reported_on": today(),
		"source": "Internal QC",
		"category": "Cabling",
		"severity": severity,
		"description": "Cable dressing incomplete on the DC run.",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


class TestSnags(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_critical_target_closure_from_settings(self):
		snag = make_snag(self.installation, severity="Critical")
		self.assertEqual(
			frappe.utils.date_diff(snag.target_closure_date, snag.reported_on), 3
		)

	def test_safety_defects_default_to_critical(self):
		"""Safety and earthing defects are what hurt people."""
		snag = make_snag(self.installation, category="Safety", severity=None)
		self.assertEqual(snag.severity, "Critical")

	def test_open_snags_roll_onto_the_installation(self):
		make_snag(self.installation, severity="Critical")
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(doc.open_snag_count, 1)
		self.assertEqual(doc.critical_snag_count, 1)

	def test_open_major_snag_blocks_pcr(self):
		"""The ministry can deactivate a vendor over unresolved defects."""
		capture_serials(self.installation, modules=6, inverters=1)
		complete_through(self.installation, CHAIN_TO_PCR)
		make_snag(self.installation, severity="Major")

		attach_stage_documents(self.installation, "PCR")
		with self.assertRaises(frappe.ValidationError) as ctx:
			stages.advance_stage(self.installation.name, "PCR")
		self.assertIn("snag", str(ctx.exception).lower())

	def test_resolved_snag_releases_pcr(self):
		capture_serials(self.installation, modules=6, inverters=1)
		complete_through(self.installation, CHAIN_TO_PCR)
		snag = make_snag(self.installation, severity="Major")
		snag.status = "Resolved"
		snag.save(ignore_permissions=True)

		attach_stage_documents(self.installation, "PCR")
		stages.advance_stage(self.installation.name, "PCR")
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(
			next(r.status for r in doc.stages if r.stage_code == "PCR"), "Completed"
		)


class TestSubsidyClaim(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		capture_serials(self.installation, modules=6, inverters=1)

	def make_claim(self, **kwargs):
		values = {
			"doctype": "Subsidy Claim",
			"company": self.installation.company,
			"solar_installation": self.installation.name,
			"expected_subsidy_amount": 78000,
			"claim_model": "Customer Claims Directly",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		return doc.insert(ignore_permissions=True)

	def test_pcr_blocked_before_commissioning(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			claim = self.make_claim(pcr_uploaded_on=today(), pcr_reference_no="PCR-1")
			claim.submit()
		self.assertIn("commission", str(ctx.exception).lower())

	def test_company_funded_gap_tracks_the_recovery(self):
		claim = self.make_claim(
			claim_model="Company Funded Gap", amount_recoverable_from_customer=78000
		)
		self.assertEqual(claim.outstanding_recovery, 78000)
		self.assertEqual(claim.recovery_status, "Pending")

		claim.amount_recovered = 30000
		claim.save(ignore_permissions=True)
		self.assertEqual(claim.outstanding_recovery, 48000)
		self.assertEqual(claim.recovery_status, "Partially Recovered")

		claim.amount_recovered = 78000
		claim.save(ignore_permissions=True)
		self.assertEqual(claim.recovery_status, "Fully Recovered")

	def test_direct_claim_records_no_recovery(self):
		claim = self.make_claim()
		self.assertEqual(claim.recovery_status, "Not Applicable")
		self.assertEqual(claim.outstanding_recovery, 0)

	def test_one_claim_per_installation(self):
		self.make_claim()
		with self.assertRaises(frappe.ValidationError):
			self.make_claim()

	def test_module_posts_no_accounting_entry(self):
		"""Grep the module and prove it."""
		import pathlib

		module = pathlib.Path(frappe.get_app_path("a3_sola", "solar_operations"))
		api = pathlib.Path(frappe.get_app_path("a3_sola", "api"))
		banned = ("Journal Entry", "Payment Entry", "GL Entry")
		offenders = []
		for path in list(module.rglob("*.py")) + [
			api / f for f in ("stages.py", "documents.py", "serials.py", "materials.py", "escalation.py")
		]:
			text = path.read_text()
			for term in banned:
				if f'"{term}"' in text or f"'{term}'" in text:
					offenders.append(f"{path.name}: {term}")
		self.assertEqual(offenders, [], f"Operations must post nothing: {offenders}")


class TestStatutoryFeePayment(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def make_payment(self, fee_type="Registration Fee", **kwargs):
		values = {
			"doctype": "Statutory Fee Payment",
			"company": self.installation.company,
			"solar_installation": self.installation.name,
			"fee_type": fee_type,
			"paid_by": "Company on Behalf of Customer",
			"payment_date": today(),
			"receipt": "/files/receipt.pdf",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		return doc.insert(ignore_permissions=True)

	def test_amounts_resolved_from_the_schedule_not_typed(self):
		payment = self.make_payment(amount_gross=999999)
		self.assertEqual(payment.amount_base, 3000)
		self.assertEqual(payment.amount_gross, 3540)
		self.assertEqual(payment.refundable_amount, 2400)

	def test_application_fee_is_not_refundable(self):
		payment = self.make_payment(fee_type="Application Fee")
		self.assertEqual(payment.amount_gross, 1180)
		self.assertEqual(payment.refundable_amount, 0)

	def test_company_paid_fee_is_reimbursable(self):
		payment = self.make_payment()
		self.assertEqual(payment.reimbursable_from_customer, 3540)
		self.assertEqual(payment.reimbursement_status, "Pending")

	def test_customer_paid_fee_is_not_reimbursable(self):
		payment = self.make_payment(paid_by="Customer Directly", receipt=None)
		self.assertEqual(payment.reimbursable_from_customer, 0)
		self.assertEqual(payment.reimbursement_status, "Not Applicable")

	def test_receipt_required_when_the_company_paid(self):
		payment = self.make_payment(receipt=None)
		with self.assertRaises(frappe.ValidationError) as ctx:
			payment.submit()
		self.assertIn("receipt", str(ctx.exception).lower())

	def test_short_refund_is_flagged(self):
		payment = self.make_payment()
		payment.submit()
		payment.refund_claimed_on = today()
		payment.refund_received_on = today()
		payment.refund_received_amount = 1000
		payment.save(ignore_permissions=True)
		self.assertEqual(payment.refund_status, "Short Received")
		self.assertEqual(payment.refund_variance, -1400)
