# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Building a job's tasks from the template, and deriving its status from them.

Transitions - completing, skipping, blocking, linking a task to its document - are covered
in test_tasks.py. This file holds the engine to the shape of the task set.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.setup import seed_stages
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey
from a3_sola.tests.solar_operations.fixtures import make_installation


def task(installation, code):
	"""One task row, found by its code, never by position."""
	return next(row for row in installation.stages if row.stage_code == code)


class TestTaskSet(FrappeTestCase):
	def test_every_task_in_the_seed_is_on_the_job(self):
		installation = make_installation()
		codes = [row.stage_code for row in installation.stages]
		self.assertEqual(codes, seed_stages.TASK_CODES)
		self.assertEqual(codes[0], "ORD")
		self.assertEqual(codes[-1], "GREV")

	def test_every_task_names_the_document_it_runs_in(self):
		"""The Task button has nothing to open for a row that does not say where it runs."""
		installation = make_installation()
		for row in installation.stages:
			self.assertTrue(row.task_doctype, f"{row.stage_code} has no executing doctype")
			self.assertTrue(frappe.db.exists("DocType", row.task_doctype), row.task_doctype)

	def test_self_funded_job_pre_skips_the_bank_tasks_with_a_reason(self):
		"""Skipped, not omitted - an auditor needs to see why there is no bank letter."""
		installation = make_installation(is_financed=0)
		skipped = {r.stage_code: r.skip_reason for r in installation.stages if r.status == "Skipped"}
		for code in ("LOAN", "BCOM"):
			self.assertIn(code, skipped)
			self.assertIn("Self-funded", skipped[code])
		# The advance and the balance are paid either way; only who pays changes.
		self.assertNotIn("ADV", skipped)
		self.assertNotIn("BAL", skipped)

	def test_financed_job_keeps_the_bank_tasks(self):
		installation = make_installation(is_financed=1)
		statuses = {r.stage_code: r.status for r in installation.stages}
		for code in ("LOAN", "BCOM"):
			self.assertNotEqual(statuses[code], "Skipped")

	def test_unsubsidised_job_pre_skips_the_portal_and_subsidy_tasks(self):
		consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey, subsidy_scheme=None, submit=True)
		installation = make_installation(consumer, estimate, subsidy_scheme=None)
		skipped = {r.stage_code for r in installation.stages if r.status == "Skipped"}
		for code in ("NPA", "PORTUPD", "SUBREQ", "CORR", "DBT"):
			self.assertIn(code, skipped)

	def test_small_job_pre_skips_the_inspectorate(self):
		"""CEIG applies above a configurable capacity threshold, not to every job."""
		installation = make_installation()
		ceig = task(installation, "CEIG")
		self.assertEqual(ceig.status, "Skipped")
		self.assertIn("threshold", ceig.skip_reason.lower())

	def test_rental_meter_pre_skips_the_purchase_tasks(self):
		installation = make_installation(net_meter_mode="Availed from DISCOM on Rental")
		for code in ("MTR", "MTRPAY"):
			self.assertEqual(task(installation, code).status, "Skipped")

	def test_planned_dates_accumulate_from_the_order_date(self):
		installation = make_installation()
		dates = [r.planned_date for r in installation.stages]
		self.assertEqual(dates, sorted(dates))

	def test_the_register_expects_documents_for_every_task_skipped_ones_included(self):
		"""A skipped task can be un-skipped; its expected documents should be waiting."""
		installation = make_installation(is_financed=0)
		codes = {r.stage_code for r in installation.documents}
		self.assertIn("ORD", codes)
		self.assertIn("KFORMS", codes)
		self.assertIn("LOAN", codes)
		self.assertTrue(all(r.document_kind == "Expected" for r in installation.documents))

	def test_the_form2_window_is_anchored_to_the_form1_fee(self):
		installation = make_installation()
		row = task(installation, "KFORMS")
		self.assertEqual(row.due_anchor_task, "F1PAY")
		self.assertEqual(row.due_anchor_days, 30)


class TestDerivedStatus(FrappeTestCase):
	def test_nothing_starts_on_submit(self):
		"""Tasks are independent. A job begins with every task Pending and nobody's focus forced."""
		installation = make_installation()
		self.assertFalse([r for r in installation.stages if r.status == "In Progress"])
		self.assertEqual(installation.status, "In Progress")
		self.assertEqual(installation.overall_progress_percent, 0)
		self.assertEqual(installation.current_stage, "Order Received")

	def test_the_focus_task_is_the_first_open_one(self):
		installation = make_installation()
		task(installation, "ORD").status = "Completed"
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		self.assertEqual(installation.current_stage, "Form 1 Generation")

	def test_a_blocked_task_takes_the_focus_wherever_it_sits(self):
		installation = make_installation()
		task(installation, "KFORMS").status = "Blocked"
		task(installation, "KFORMS").blocked_reason = "Section office closed for audit"
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		self.assertEqual(installation.status, "Blocked")
		self.assertEqual(installation.current_stage, "Form 2 & 3 Submission")
		self.assertEqual(installation.blocking_party, "Internal")

	def test_awaiting_external_only_when_every_active_task_is_external(self):
		installation = make_installation()
		task(installation, "CEIG").status = "In Progress"
		task(installation, "CEIG").skip_reason = None
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		self.assertEqual(installation.status, "Awaiting External")

		task(installation, "FRM1").status = "In Progress"
		installation.save(ignore_permissions=True)
		self.assertEqual(installation.status, "In Progress")

	def test_progress_counts_only_applicable_mandatory_tasks(self):
		installation = make_installation()
		task(installation, "ORD").status = "Completed"
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		self.assertGreater(installation.overall_progress_percent, 0)
		self.assertLess(installation.overall_progress_percent, 100)

	def test_closed_when_every_mandatory_task_is_done(self):
		installation = make_installation()
		for row in installation.stages:
			if row.status != "Skipped" and row.is_mandatory:
				row.status = "Completed"
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		self.assertEqual(installation.status, "Closed")

	def test_an_anchored_task_is_due_a_window_after_its_anchor_completes(self):
		installation = make_installation()
		anchor = task(installation, "F1PAY")
		anchor.status = "Completed"
		anchor.actual_completion_date = frappe.utils.today()
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		self.assertEqual(
			str(task(installation, "KFORMS").due_date), frappe.utils.add_days(frappe.utils.today(), 30)
		)
