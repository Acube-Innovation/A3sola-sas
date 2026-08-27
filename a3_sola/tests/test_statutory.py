# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Statutory fees - the regression anchor is the client's own 3 kW proposal."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import statutory


class TestStatutoryFees(FrappeTestCase):
	def test_three_kw_matches_the_clients_own_proposal(self):
		"""The one combination the client's existing templates get right.

		Their 3 kW proposal states an application fee of Rs 1,180, a registration fee of
		Rs 3,540 and Rs 2,400 refundable. That is Rs 1,000/kW + 18% GST with 80% of the
		base refunded, and it is the rule the whole fee model is built on.
		"""
		fees = statutory.get_statutory_fees("KSEB", "Single Phase", 3, "Purchased by Customer")
		self.assertEqual(fees["application_fee_gross"], 1180)
		self.assertEqual(fees["registration_fee_base"], 3000)
		self.assertEqual(fees["registration_fee_gross"], 3540)
		self.assertEqual(fees["registration_refundable"], 2400)
		self.assertEqual(fees["net_meter_charge"], 5000)

	def test_ten_kw_refund_is_computed_not_transcribed(self):
		"""The client's 10 kW template prints Rs 4,000 refundable. It should be Rs 8,000.

		This test exists to make that class of transcription error impossible to reintroduce.
		"""
		fees = statutory.get_statutory_fees("KSEB", "Three Phase", 10, "Purchased by Customer")
		self.assertEqual(fees["registration_fee_gross"], 11800)
		self.assertEqual(fees["registration_refundable"], 8000)
		self.assertNotEqual(fees["registration_refundable"], 4000)

	def test_net_meter_from_discom_reports_lead_time_not_a_price(self):
		fees = statutory.get_statutory_fees("KSEB", "Single Phase", 5, "Availed from DISCOM on Rental")
		self.assertEqual(fees["net_meter_charge"], 0)
		self.assertEqual(fees["net_meter_allocation_lead_days"], 21)
		note = " ".join(row["note"] for row in fees["breakdown"])
		self.assertIn("rental", note.lower())

	def test_breakdown_names_the_refundable_amount(self):
		fees = statutory.get_statutory_fees("KSEB", "Single Phase", 3, "Purchased by Customer")
		registration = next(r for r in fees["breakdown"] if "Registration" in r["item"])
		self.assertIn("2400", registration["note"].replace(",", ""))

	def test_missing_schedule_raises_rather_than_quoting_zero(self):
		"""A silently zero fee reaches a customer proposal."""
		with self.assertRaises(frappe.ValidationError):
			statutory.get_statutory_fees("KSEB", "Single Phase", 3, "Purchased by Customer", on_date="2001-01-01")

	def test_refund_due_matches_the_fee_computation(self):
		fees = statutory.get_statutory_fees("KSEB", "Three Phase", 8, "Purchased by Customer")
		refund = statutory.get_refund_due("KSEB", "Three Phase", 8, "Purchased by Customer")
		self.assertEqual(refund["refundable_amount"], fees["registration_refundable"])
		self.assertEqual(refund["refundable_amount"], 6400)
