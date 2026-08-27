# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The eligibility rule registry and its waivers."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_crm.doctype.subsidy_eligibility_check.subsidy_eligibility_check import waive_rule
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey, scheme


def make_check(consumer, estimate=None):
	doc = frappe.get_doc(
		{
			"doctype": "Subsidy Eligibility Check",
			"company": consumer.company,
			"solar_consumer": consumer.name,
			"design_estimate": estimate.name if estimate else None,
			"subsidy_scheme": scheme(consumer.company),
		}
	)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


class TestEligibility(FrappeTestCase):
	def setUp(self):
		self.consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		self.survey = make_survey(self.consumer, segments=((240, True),))
		self.estimate = make_estimate(self.consumer, self.survey)

	def test_every_rule_is_evaluated(self):
		check = make_check(self.consumer, self.estimate)
		codes = [row.rule_code for row in check.rule_results]
		self.assertEqual(len(codes), 11)
		self.assertEqual(codes, sorted(codes))
		self.assertIn("ELG-09", codes)

	def test_prior_subsidy_makes_it_not_eligible(self):
		consumer = make_consumer(
			has_availed_prior_subsidy=1, prior_scheme_name="PM Surya Ghar", prior_subsidy_year=2024
		)
		check = make_check(consumer)
		self.assertEqual(check.overall_result, "Not Eligible")
		row = next(r for r in check.rule_results if r.rule_code == "ELG-02")
		self.assertEqual(row.result, "Fail")
		self.assertIn("2024", row.remarks)

	def test_missing_bank_details_fail_elg_09(self):
		"""Without an account the DBT cannot land and the refund cannot be claimed."""
		consumer = make_consumer(bank_account_no=None, bank_ifsc_code=None, bank_account_holder_name=None)
		check = make_check(consumer)
		row = next(r for r in check.rule_results if r.rule_code == "ELG-09")
		self.assertEqual(row.result, "Fail")
		self.assertEqual(check.overall_result, "Not Eligible")

	def test_ehs_blocked_survey_fails_elg_10(self):
		consumer = make_consumer()
		survey = make_survey(consumer, submit=False, asbestos_present=1)
		survey.save()
		estimate = make_estimate(consumer, survey)
		check = make_check(consumer, estimate)
		row = next(r for r in check.rule_results if r.rule_code == "ELG-10")
		self.assertEqual(row.result, "Fail")

	def test_phase_rule_follows_the_stay_on_the_check_date(self):
		"""The KSERC three-phase rule was stayed until 22.05.2026 and bites after it.

		A back-dated check must reflect the law that applied then, so the same 5 kW
		single-phase job is Not Applicable inside the stay and Fail after it.
		"""
		consumer = make_consumer(
			avg_consumption_units=1250, sanctioned_load_kw=10, connection_type="Single Phase"
		)
		survey = make_survey(consumer, segments=((400, True),))
		estimate = make_estimate(consumer, survey)

		during = make_check(consumer, estimate)
		during.check_date = "2026-01-15"
		during.save()
		row = next(r for r in during.rule_results if r.rule_code == "ELG-08")
		self.assertEqual(row.result, "Not Applicable")
		self.assertIn("stayed", row.remarks.lower())

		after = make_check(consumer, estimate)
		after.check_date = "2026-06-01"
		after.save()
		row = next(r for r in after.rule_results if r.rule_code == "ELG-08")
		self.assertEqual(row.result, "Fail")

	def test_waiver_produces_eligible_with_conditions(self):
		consumer = make_consumer(
			avg_consumption_units=750, sanctioned_load_kw=5,
			has_availed_prior_subsidy=1, prior_scheme_name="PM Surya Ghar",
		)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey)
		check = make_check(consumer, estimate)
		self.assertEqual(check.overall_result, "Not Eligible")

		result = waive_rule(check.name, "ELG-02", "Prior claim was on a different premises; letter on file.")
		self.assertEqual(result, "Eligible with Conditions")

		check.reload()
		row = next(r for r in check.rule_results if r.rule_code == "ELG-02")
		self.assertEqual(row.result, "Waived")
		self.assertEqual(row.waived_by, frappe.session.user)

	def test_waiver_survives_recomputation(self):
		"""A recomputation must not silently revoke a manager's decision."""
		consumer = make_consumer(
			avg_consumption_units=750, sanctioned_load_kw=5, has_availed_prior_subsidy=1
		)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey)
		check = make_check(consumer, estimate)
		waive_rule(check.name, "ELG-02", "Documented exception.")
		check.reload()
		check.save()
		row = next(r for r in check.rule_results if r.rule_code == "ELG-02")
		self.assertEqual(row.result, "Waived")
		self.assertEqual(check.overall_result, "Eligible with Conditions")

	def test_waiver_requires_a_reason(self):
		check = make_check(self.consumer, self.estimate)
		with self.assertRaises(frappe.ValidationError):
			waive_rule(check.name, "ELG-02", "   ")

	def test_results_are_not_hand_settable(self):
		"""Overwritten from the registry on every validate."""
		check = make_check(self.consumer, self.estimate)
		row = next(r for r in check.rule_results if r.rule_code == "ELG-01")
		row.result = "Fail"
		check.save()
		row = next(r for r in check.rule_results if r.rule_code == "ELG-01")
		self.assertEqual(row.result, "Pass")
