# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Install and seeding.

`after_install` and `after_migrate` both call `setup()`, so it must be idempotent: running
it again on a seeded site must change nothing. This is the property that lets a partially
seeded site converge instead of erroring, and it is what makes `after_migrate` safe.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.setup import install

SEEDED = [
	("DISCOM", 1),
	("DISCOM Section", 19),
	("Roof Type", 4),
	("Subsidy Scheme", 2),
	("Electricity Tariff", 1),
	("Statutory Fee Schedule", 1),
	("Grid Regulation Rule", 1),
	("Component Make", 17),
	("Outreach Message Template", 5),
	("Solar Package", 10),
]


class TestSeeding(FrappeTestCase):
	def company(self):
		return install.default_company()

	def test_every_master_is_seeded_for_the_default_company(self):
		company = self.company()
		for doctype, expected in SEEDED:
			actual = frappe.db.count(doctype, {"company": company})
			self.assertEqual(actual, expected, f"{doctype}: expected {expected}, found {actual}")

	def test_seeding_is_idempotent(self):
		company = self.company()
		before = {dt: frappe.db.count(dt, {"company": company}) for dt, _ in SEEDED}
		install.seed_masters(company)
		after = {dt: frappe.db.count(dt, {"company": company}) for dt, _ in SEEDED}
		self.assertEqual(before, after, "re-seeding created duplicates")

	def test_settings_singleton_is_the_only_one(self):
		"""Phases 2 to 7 add tabs to this doctype; they never create a second one."""
		singles = frappe.get_all(
			"DocType", filters={"module": "Solar CRM", "issingle": 1}, pluck="name"
		)
		self.assertEqual(singles, ["A3 Sola Settings"])

	def test_settings_carry_the_proposal_text_and_scope(self):
		settings = frappe.get_single("A3 Sola Settings")
		self.assertTrue(settings.covering_letter_text)
		self.assertTrue(settings.terms_and_conditions_text)
		self.assertEqual(len(settings.scope_of_work), 9)
		self.assertEqual(len(settings.brand_social_links), 7)
		self.assertEqual(len(settings.outreach_cadence), 5)

	def test_custom_fields_are_module_scoped(self):
		"""So `bench export-fixtures` does not drag unrelated records in."""
		for doctype in ("Company", "Lead", "Quotation", "Item", "Opportunity", "Sales Order"):
			fields = frappe.get_all(
				"Custom Field", filters={"dt": doctype, "module": "Solar CRM"}, pluck="name"
			)
			self.assertTrue(fields, f"no module-scoped custom fields on {doctype}")

	def test_the_subsidy_display_field_carries_its_warning(self):
		description = frappe.db.get_value(
			"Custom Field", "Quotation-expected_subsidy_to_customer", "description"
		)
		self.assertIn("DISPLAY ONLY", description)
		self.assertIn("never appear", description)
