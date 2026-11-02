# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Compare options: how many panels and inverters each option takes, the option that costs
least marked, and the comparison sent to the customer as a part of the estimate."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_estimate, portal_share
from a3_sola.tests.fixtures import make_consumer, make_estimate


def column(key, total, error=None):
	return {"key": key, "total": total, "error": error}


class TestEstimateComparison(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_each_option_says_how_many_panels_and_inverters(self):
		estimate = make_estimate(make_consumer())
		columns = portal_estimate.comparison(estimate)
		priced = [c for c in columns if not c.get("error") and c.get("panel")]
		if not priced:
			self.skipTest("The site has no fixture package to build a kit from.")
		for c in priced:
			self.assertTrue(float(c["panel_nos"]) > 0)
			self.assertTrue(float(c["inverter_nos"]) > 0)

	def test_the_cheapest_option_is_marked(self):
		self.assertEqual(portal_estimate.lowest_keys([column("a", 300), column("b", 250), column("c", 280)]), ["b"])

	def test_a_tie_for_cheapest_marks_both(self):
		self.assertEqual(portal_estimate.lowest_keys([column("a", 250), column("b", 250), column("c", 280)]), ["a", "b"])

	def test_nothing_is_marked_without_a_choice(self):
		self.assertEqual(portal_estimate.lowest_keys([column("a", 250)]), [])
		self.assertEqual(portal_estimate.lowest_keys([column("a", 250), column("b", 250)]), [])
		# An option that cannot be worked out is not in the running.
		self.assertEqual(portal_estimate.lowest_keys([column("a", 250), column("b", 0, error="No package")]), [])

	def test_the_comparison_is_a_part_of_an_estimate_only(self):
		estimate = frappe._dict(doctype="Solar Design Estimate")
		self.assertEqual(portal_share._part(estimate, portal_share.COMPARISON), portal_share.COMPARISON)
		with self.assertRaises(frappe.PermissionError):
			portal_share._part(frappe._dict(doctype="Quotation"), portal_share.COMPARISON)
