# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The three-phase rule and its High Court stay."""

from frappe.tests.utils import FrappeTestCase

from a3_sola.api import regulation


class TestGridRegulation(FrappeTestCase):
	def test_stay_in_force_does_not_fail_a_single_phase_quotation(self):
		"""A court stay must not silently fail every 5 kW single-phase quotation."""
		result = regulation.check_connection_type(5, "Single Phase", "KSEB", on_date="2026-01-15")
		self.assertTrue(result["compliant"])
		self.assertTrue(result["stayed"])
		self.assertIn("stayed", result["message"].lower())

	def test_rule_bites_once_the_stay_expires(self):
		result = regulation.check_connection_type(5, "Single Phase", "KSEB", on_date="2026-06-01")
		self.assertFalse(result["compliant"])
		self.assertEqual(result["required_type"], "Three Phase")

	def test_below_threshold_is_always_compliant(self):
		result = regulation.check_connection_type(3, "Single Phase", "KSEB", on_date="2026-06-01")
		self.assertTrue(result["compliant"])

	def test_three_phase_is_compliant_after_the_stay(self):
		result = regulation.check_connection_type(5, "Three Phase", "KSEB", on_date="2026-06-01")
		self.assertTrue(result["compliant"])

	def test_customer_clause_comes_from_the_rule(self):
		"""The proposal sentence is data, so it cannot go stale."""
		clauses = regulation.get_customer_clauses("KSEB", on_date="2026-06-01")
		self.assertTrue(clauses)
		self.assertIn("three-phase", clauses[0]["clause"].lower())
