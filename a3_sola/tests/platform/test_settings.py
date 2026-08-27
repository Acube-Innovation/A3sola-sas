# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The one settings singleton.

Every phase adds a tab to A3 Sola Settings. A field added twice under the same name is
silently ignored by Frappe - the first wins - so the second phase's default never applies
and nobody finds out until a template renders the wrong string. This is the guard.
"""

import collections

import frappe
from frappe.tests.utils import FrappeTestCase

EXPECTED_TABS = ("General", "CRM", "Operations", "Projects", "Platform")


class TestSettingsSingleton(FrappeTestCase):
	def setUp(self):
		self.meta = frappe.get_meta("A3 Sola Settings")

	def test_no_fieldname_appears_twice(self):
		counts = collections.Counter(f.fieldname for f in self.meta.fields)
		duplicates = {name: n for name, n in counts.items() if n > 1}
		self.assertEqual(
			duplicates, {}, f"a later phase shadowed an existing field: {duplicates}"
		)

	def test_there_is_still_only_one_singleton(self):
		singles = frappe.get_all(
			"DocType",
			filters={
				"issingle": 1,
				"module": ["in", ["Solar CRM", "Solar Operations", "Solar Projects", "Platform"]],
			},
			pluck="name",
		)
		self.assertEqual(singles, ["A3 Sola Settings"])

	def test_every_phase_has_its_tab(self):
		tabs = [f.label for f in self.meta.fields if f.fieldtype == "Tab Break"]
		for expected in EXPECTED_TABS:
			self.assertIn(expected, tabs, f"the {expected} tab is missing")

	def test_the_platform_fields_are_all_present(self):
		for fieldname in (
			"signup_series_prefix", "demo_request_series_prefix", "product_tagline",
			"partner_badge_text", "sales_email", "enable_public_signup",
			"enable_demo_requests", "maintenance_mode", "enable_analytics",
		):
			self.assertTrue(
				self.meta.get_field(fieldname), f"Platform field {fieldname} is missing"
			)

	def test_public_signup_and_demo_requests_default_on(self):
		for fieldname in ("enable_public_signup", "enable_demo_requests"):
			self.assertEqual(self.meta.get_field(fieldname).default, "1")

	def test_analytics_and_maintenance_default_off(self):
		"""Analytics without consent, and a maintenance page nobody asked for, are both wrong."""
		self.assertIn(self.meta.get_field("enable_analytics").default, (None, "", "0"))
		self.assertIn(self.meta.get_field("maintenance_mode").default, (None, "", "0"))
