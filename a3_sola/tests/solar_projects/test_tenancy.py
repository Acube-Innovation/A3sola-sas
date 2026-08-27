# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Multi-tenant isolation for Solar Projects.

The money layer is where a leak between tenants does the most damage, so this extends the
Phase 1 registry guard rather than repeating it: every doctype registered, every one with a
company field isolated, and no posting able to reach another company's ledger.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import permissions
from a3_sola.registry import solar_projects
from a3_sola.tests.fixtures import default_company, make_company
from a3_sola.tests.solar_projects.fixtures import commissioned_project


class TestProjectsRegistry(FrappeTestCase):
	def test_every_projects_doctype_is_registered(self):
		on_disk = set(frappe.get_all("DocType", filters={"module": "Solar Projects"}, pluck="name"))
		registered = set(solar_projects.DOCTYPES)
		self.assertEqual(
			on_disk - registered, set(), "doctypes exist that the registry does not declare"
		)

	def test_every_company_bearing_doctype_is_isolated(self):
		missing = []
		for doctype in solar_projects.DOCTYPES:
			meta = frappe.get_meta(doctype)
			if meta.istable or not meta.has_field("company"):
				continue
			if doctype not in solar_projects.PERMISSION_DOCTYPES:
				missing.append(doctype)
		self.assertEqual(missing, [], f"unisolated doctypes: {missing}")

	def test_permission_doctypes_all_carry_a_company_field(self):
		for doctype in solar_projects.PERMISSION_DOCTYPES:
			self.assertTrue(
				frappe.get_meta(doctype).has_field("company"),
				f"{doctype} is registered for isolation but has no company field",
			)

	def test_hooks_registered_for_every_permission_doctype(self):
		query_hooks = frappe.get_hooks("permission_query_conditions") or {}
		row_hooks = frappe.get_hooks("has_permission") or {}
		for doctype in solar_projects.PERMISSION_DOCTYPES:
			self.assertIn(doctype, query_hooks, f"{doctype} has no query condition hook")
			self.assertIn(doctype, row_hooks, f"{doctype} has no row permission hook")

	def test_scheduler_targets_all_resolve(self):
		"""A scheduler entry pointing at nothing fails silently every night."""
		for _event, methods in solar_projects.SCHEDULER_EVENTS.items():
			for method in methods:
				self.assertTrue(callable(frappe.get_attr(method)), f"{method} is not callable")

	def test_doc_event_targets_all_resolve(self):
		for _doctype, events in solar_projects.DOC_EVENTS.items():
			for _event, methods in events.items():
				for method in methods:
					self.assertTrue(callable(frappe.get_attr(method)), f"{method} is not callable")

	def test_the_app_declares_only_the_planned_modules(self):
		"""One app, four modules and no more. A fifth would mean the plan slipped."""
		import os

		import a3_sola

		path = os.path.join(os.path.dirname(a3_sola.__file__), "modules.txt")
		with open(path) as handle:
			modules = [line.strip() for line in handle if line.strip()]
		self.assertEqual(
			modules, ["Solar CRM", "Solar Operations", "Solar Projects", "Platform"]
		)

	def test_there_is_still_exactly_one_settings_singleton(self):
		singles = frappe.get_all(
			"DocType",
			filters={
				"issingle": 1,
				"module": ["in", ["Solar CRM", "Solar Operations", "Solar Projects", "Platform"]],
			},
			pluck="name",
		)
		self.assertEqual(singles, ["A3 Sola Settings"])


class TestProjectsIsolation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company_a = default_company()
		cls.company_b = make_company("Solar Projects Tenant B", "SPB")
		frappe.db.commit()

	def test_a_project_only_sees_its_own_tenants_masters(self):
		for company in (self.company_a, self.company_b):
			self.assertTrue(
				frappe.db.exists("Billing Milestone Template", {"company": company, "is_default": 1}),
				f"{company} has no default milestone template",
			)

	def test_cost_categories_are_seeded_for_every_tenant(self):
		settings = frappe.get_single("A3 Sola Settings")
		self.assertTrue(settings.cost_categories, "no cost categories configured")
		self.assertIn(
			"Statutory Fees",
			{row.category_name for row in settings.cost_categories if row.is_pass_through},
		)

	def test_account_mapping_scaffolded_for_every_tenant(self):
		settings = frappe.get_single("A3 Sola Settings")
		mapped = {row.company for row in settings.solar_account_mapping}
		for company in (self.company_a, self.company_b):
			self.assertIn(company, mapped, f"{company} has no account mapping row")

	def test_a_cross_company_link_is_rejected_and_named(self):
		"""An O&M contract must never reach across into another tenant's project."""
		project, _installation, _ = commissioned_project()
		with self.assertRaises(frappe.ValidationError) as caught:
			frappe.get_doc(
				{
					"doctype": "Service Ticket",
					"company": self.company_b,
					"om_contract": frappe.db.get_value(
						"Solar OM Contract", {"project": project.name}, "name"
					),
					"reported_on": frappe.utils.now_datetime(),
					"reported_via": "Phone",
					"category": "Low Generation",
					"description": "Cross-tenant attempt.",
				}
			).insert(ignore_permissions=True)
		self.assertIn(self.company_a, str(caught.exception))


class TestDocumentedSchedulersAreReal(FrappeTestCase):
	"""The README names every scheduler. A job in the table that does not exist, or one
	that exists but is not in the table, is a lie in the documentation."""

	def _readme(self):
		import os

		import a3_sola

		path = os.path.join(os.path.dirname(os.path.dirname(a3_sola.__file__)), "README.md")
		with open(path) as handle:
			return handle.read()

	def test_every_documented_job_exists(self):
		import re

		for method in set(re.findall(r"`(a3_sola\.api\.[a-z_]+\.[a-z_]+)`", self._readme())):
			self.assertTrue(callable(frappe.get_attr(method)), f"{method} is documented but absent")

	def test_every_registered_job_is_documented(self):
		readme = self._readme()
		for _cadence, methods in solar_projects.SCHEDULER_EVENTS.items():
			for method in methods:
				self.assertIn(method, readme, f"{method} runs nightly and is undocumented")
