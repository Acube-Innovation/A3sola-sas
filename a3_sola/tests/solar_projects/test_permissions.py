# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A service technician must never see money.

Not contract value, not margin, not the provision, not what a warranty claim was worth.
Every Currency field in this module sits at permlevel 1 and the grant is explicit - so
this asserts both halves: that the fields are guarded, and that only the right roles hold
the key.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.registry import solar_projects
from a3_sola.setup.install_projects import FINANCIAL_ROLES, PROJ_ROLES

#: Fields on Project that Phase 3 adds and guards.
PROJECT_GUARDED = (
	"gross_contract_value",
	"total_billed_amount",
	"total_cost",
	"gross_margin_amount",
	"om_provision_amount",
)


class TestFinancialFieldsAreGuarded(FrappeTestCase):
	def test_every_currency_field_sits_at_permlevel_one(self):
		unguarded = {}
		for doctype in solar_projects.DOCTYPES:
			meta = frappe.get_meta(doctype)
			if meta.istable:
				continue
			loose = [
				field.fieldname
				for field in meta.fields
				if field.fieldtype == "Currency" and not field.permlevel
			]
			if loose:
				unguarded[doctype] = loose
		self.assertEqual(unguarded, {}, f"currency fields readable by anyone: {unguarded}")

	def test_project_costing_fields_are_guarded(self):
		meta = frappe.get_meta("Project")
		for fieldname in PROJECT_GUARDED:
			field = meta.get_field(fieldname)
			self.assertTrue(field, f"Project has no field {fieldname}")
			self.assertEqual(field.permlevel, 1, f"Project.{fieldname} is readable by anyone")

	def test_the_cost_entry_table_is_guarded(self):
		field = frappe.get_meta("Project").get_field("cost_entries")
		self.assertEqual(field.permlevel, 1)


class TestWhoHoldsTheKey(FrappeTestCase):
	def _level_one_roles(self, doctype):
		return {
			row.role for row in frappe.get_meta(doctype).permissions if row.permlevel == 1
		}

	def test_only_the_financial_roles_are_granted_level_one(self):
		for doctype in solar_projects.DOCTYPES:
			meta = frappe.get_meta(doctype)
			if meta.istable or not any(f.permlevel for f in meta.fields):
				continue
			granted = self._level_one_roles(doctype)
			self.assertTrue(granted, f"{doctype} guards fields nobody can read")
			self.assertEqual(
				granted - set(FINANCIAL_ROLES),
				set(),
				f"{doctype} grants level 1 beyond the financial roles",
			)

	def test_the_technician_is_never_granted_level_one(self):
		for doctype in solar_projects.DOCTYPES:
			meta = frappe.get_meta(doctype)
			if meta.istable:
				continue
			self.assertNotIn(
				"Solar Service Technician",
				self._level_one_roles(doctype),
				f"a technician can read money on {doctype}",
			)
		self.assertNotIn("Solar Service Technician", FINANCIAL_ROLES)

	def test_the_coordinator_is_never_granted_level_one(self):
		"""Full ticket handling, read-only on financials - which means not at level 1."""
		for doctype in solar_projects.DOCTYPES:
			meta = frappe.get_meta(doctype)
			if meta.istable:
				continue
			self.assertNotIn("Solar Service Coordinator", self._level_one_roles(doctype))

	def test_project_level_one_is_granted_to_the_financial_roles(self):
		"""Added to, not replaced.

		ERPNext already grants level 1 on Project to its own project roles for its own
		costing fields. This app adds the solar financial roles alongside them; taking
		ERPNext's away would break the standard product.
		"""
		granted = set(
			frappe.get_all(
				"Custom DocPerm", filters={"parent": "Project", "permlevel": 1}, pluck="role"
			)
		)
		self.assertTrue(
			set(FINANCIAL_ROLES) <= granted,
			f"missing from Project level 1: {set(FINANCIAL_ROLES) - granted}",
		)

	def test_the_service_roles_never_reach_project_level_one(self):
		granted = set(
			frappe.get_all(
				"Custom DocPerm", filters={"parent": "Project", "permlevel": 1}, pluck="role"
			)
		)
		for role in ("Solar Service Technician", "Solar Service Coordinator"):
			self.assertNotIn(role, granted)

	def test_ordinary_project_access_survives_the_grant(self):
		"""The moment a doctype has any Custom DocPerm, Frappe ignores its standard ones.

		So the level-1 grant has to copy the standard rows across first, or everyone in
		the system loses ordinary access to Project.
		"""
		level_zero = {
			row.role for row in frappe.get_meta("Project").permissions if row.permlevel == 0
		}
		self.assertTrue(level_zero, "Project has no level-0 permissions left at all")
		self.assertIn("Projects User", level_zero)

	def test_a_permlevel_zero_field_is_still_readable(self):
		"""The symptom of the bug above: get_list silently drops the fields."""
		rows = frappe.get_list(
			"Project",
			filters={"solar_installation": ["is", "set"]},
			fields=["name", "capacity_kw", "solar_consumer"],
			limit_page_length=1,
		)
		if rows:
			self.assertIn("capacity_kw", rows[0])
			self.assertIn("solar_consumer", rows[0])

	def test_every_phase_three_role_exists(self):
		for role, _description in PROJ_ROLES:
			self.assertTrue(frappe.db.exists("Role", role), f"{role} was never created")


class TestPostingRequiresAnAccountsManager(FrappeTestCase):
	def test_posting_checks_the_role_at_function_level(self):
		"""Doctype permissions are not enough - the check is inside the posting itself."""
		import inspect

		from a3_sola.api import accounting

		source = inspect.getsource(accounting)
		self.assertIn("_require_accounts_manager", source)
		for function in (
			"post_subsidy_receivable",
			"post_subsidy_recovery",
			"post_statutory_receivable",
			"post_statutory_refund",
		):
			body = inspect.getsource(getattr(accounting, function))
			self.assertIn(
				"_require_accounts_manager()",
				body,
				f"{function} posts without checking the role at function level",
			)

	def test_a_technician_cannot_post(self):
		from a3_sola.api import accounting

		user = "technician.noposting@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Tech",
					"send_welcome_email": 0,
					"roles": [{"role": "Solar Service Technician"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				accounting._require_accounts_manager()
		finally:
			frappe.set_user("Administrator")
