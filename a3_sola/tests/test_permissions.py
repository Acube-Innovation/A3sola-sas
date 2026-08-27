# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Field-level permissions.

A Survey Engineer must see no commercial figure anywhere, and nobody on site should see a
customer's bank account number - a leaked one is a fraud report, not a support ticket.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

COMMERCIAL_FIELDS = [
	"gross_system_cost",
	"total_project_cost",
	"net_cost_to_customer",
	"cost_per_kw",
	"lifetime_savings",
	"cashflow",
]
BANK_FIELDS = [
	"bank_account_holder_name",
	"bank_account_no",
	"bank_name",
	"bank_branch",
	"bank_ifsc_code",
	"cancelled_cheque",
]


class TestFieldPermissions(FrappeTestCase):
	def test_commercial_fields_are_permlevel_1(self):
		meta = frappe.get_meta("Solar Design Estimate")
		for fieldname in COMMERCIAL_FIELDS:
			df = meta.get_field(fieldname)
			self.assertIsNotNone(df, f"{fieldname} missing from Solar Design Estimate")
			self.assertEqual(df.permlevel, 1, f"{fieldname} is not permlevel 1")

	def test_consumer_bank_fields_are_permlevel_1(self):
		meta = frappe.get_meta("Solar Consumer")
		for fieldname in BANK_FIELDS:
			df = meta.get_field(fieldname)
			self.assertIsNotNone(df, f"{fieldname} missing from Solar Consumer")
			self.assertGreaterEqual(df.permlevel, 1, f"{fieldname} is not permission-gated")

	def test_survey_engineer_has_no_permlevel_1_grant_on_estimates(self):
		"""The role can read the document but not its money."""
		grants = frappe.get_all(
			"DocPerm",
			filters={"parent": "Solar Design Estimate", "role": "Solar Survey Engineer"},
			fields=["permlevel", "read", "write"],
		)
		self.assertTrue(grants, "Solar Survey Engineer has no permission row at all")
		for grant in grants:
			self.assertEqual(grant.permlevel, 0, "Survey Engineer must not hold a permlevel 1 grant")

	def test_managers_hold_the_permlevel_1_grant(self):
		roles = {
			row.role
			for row in frappe.get_all(
				"DocPerm",
				filters={"parent": "Solar Design Estimate", "permlevel": 1},
				fields=["role"],
			)
		}
		self.assertIn("Solar Sales Manager", roles)
		self.assertIn("Solar CRM Manager", roles)

	def test_roles_and_profiles_exist(self):
		for role in (
			"Solar Sales Executive",
			"Solar Survey Engineer",
			"Solar Design Engineer",
			"Solar Sales Manager",
			"Solar CRM Manager",
		):
			self.assertTrue(frappe.db.exists("Role", role), f"missing role {role}")
		self.assertTrue(frappe.db.exists("Role Profile", "Solar Sales"))
