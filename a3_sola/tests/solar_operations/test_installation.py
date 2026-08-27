# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The stage engine."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import stages
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey
from a3_sola.tests.solar_operations.fixtures import (
	attach_stage_documents,
	complete_through,
	make_installation,
)


class TestStageChain(FrappeTestCase):
	def test_chain_built_from_the_template(self):
		installation = make_installation()
		codes = [row.stage_code for row in installation.stages]
		self.assertEqual(len(codes), 19)
		self.assertEqual(codes[0], "ORD")
		self.assertEqual(codes[-1], "RFND")

	def test_self_funded_job_skips_the_loan_stages_with_a_reason(self):
		"""Skipped, not omitted - an auditor needs to see why there is no bank letter."""
		installation = make_installation(is_financed=0)
		skipped = {r.stage_code: r.skip_reason for r in installation.stages if r.status == "Skipped"}
		for code in ("VFR", "LOAN", "BCOM"):
			self.assertIn(code, skipped)
			self.assertIn("Self-funded", skipped[code])

	def test_financed_job_keeps_the_loan_stages(self):
		installation = make_installation(is_financed=1)
		statuses = {r.stage_code: r.status for r in installation.stages}
		for code in ("VFR", "LOAN", "BCOM"):
			self.assertNotEqual(statuses[code], "Skipped")

	def test_unsubsidised_job_skips_pcr_and_dbt(self):
		consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey, subsidy_scheme=None, submit=True)
		installation = make_installation(consumer, estimate, subsidy_scheme=None)
		skipped = {r.stage_code for r in installation.stages if r.status == "Skipped"}
		self.assertIn("PCR", skipped)
		self.assertIn("DBT", skipped)

	def test_small_job_skips_the_inspectorate(self):
		"""CEIG applies above a configurable capacity threshold, not to every job."""
		installation = make_installation()
		ceig = next(r for r in installation.stages if r.stage_code == "CEIG")
		self.assertEqual(ceig.status, "Skipped")
		self.assertIn("threshold", ceig.skip_reason.lower())

	def test_planned_dates_accumulate_from_the_order_date(self):
		installation = make_installation()
		dates = [r.planned_date for r in installation.stages]
		self.assertEqual(dates, sorted(dates))

	def test_checklist_populated_for_applicable_stages(self):
		installation = make_installation()
		stage_codes = {r.stage_code for r in installation.documents}
		self.assertIn("ORD", stage_codes)
		self.assertIn("KTST", stage_codes)

	def test_first_stage_starts_on_submit(self):
		installation = make_installation()
		self.assertEqual(installation.stages[0].status, "In Progress")
		self.assertEqual(installation.current_stage, "Order Received")


class TestStageTransitions(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_advance_blocked_without_evidence(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			stages.advance_stage(self.installation.name, "ORD")
		self.assertIn("not attached", str(ctx.exception))

	def test_advance_blocked_when_attached_but_unverified(self):
		attach_stage_documents(self.installation, "ORD", verified=False)
		with self.assertRaises(frappe.ValidationError) as ctx:
			stages.advance_stage(self.installation.name, "ORD")
		self.assertIn("not verified", str(ctx.exception))

	def test_advance_starts_the_next_stage(self):
		attach_stage_documents(self.installation, "ORD")
		stages.advance_stage(self.installation.name, "ORD")
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(doc.stages[0].status, "Completed")
		self.assertEqual(doc.current_stage, "National Portal Application")

	def test_block_and_unblock(self):
		stages.block_stage(self.installation.name, "ORD", "Customer has not signed the agreement")
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(doc.status, "Blocked")
		self.assertEqual(doc.blocking_party, "Internal")

		stages.unblock_stage(self.installation.name, "ORD", "Signed copy received")
		doc.reload()
		self.assertEqual(doc.stages[0].status, "In Progress")

	def test_block_requires_a_reason(self):
		with self.assertRaises(frappe.ValidationError):
			stages.block_stage(self.installation.name, "ORD", "   ")

	def test_skip_refused_for_a_mandatory_stage_without_the_manager_role(self):
		user = "ops.exec@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Ops",
					"send_welcome_email": 0,
					"roles": [{"role": "Solar Operations Executive"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				stages.skip_stage(self.installation.name, "ORD", "Not needed")
		finally:
			frappe.set_user("Administrator")

	def test_revert_clears_downstream_stages(self):
		doc = complete_through(self.installation, ["ORD", "NPA"])
		self.assertEqual(doc.stages[1].status, "Completed")

		stages.revert_stage(doc.name, "ORD", "Agreement re-executed")
		doc.reload()
		self.assertEqual(doc.stages[0].status, "In Progress")
		self.assertEqual(doc.stages[1].status, "Pending")
		self.assertIsNone(doc.stages[1].actual_completion_date)

	def test_status_awaiting_external_at_a_discom_stage(self):
		doc = complete_through(self.installation, ["ORD", "NPA"])
		self.assertEqual(doc.current_stage_owner_type, "DISCOM")
		self.assertEqual(doc.status, "Awaiting External")

	def test_progress_counts_only_applicable_mandatory_stages(self):
		doc = complete_through(self.installation, ["ORD"])
		self.assertGreater(doc.overall_progress_percent, 0)
		self.assertLess(doc.overall_progress_percent, 100)
