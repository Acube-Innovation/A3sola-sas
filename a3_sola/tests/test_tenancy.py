# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Multi-tenant isolation - the highest-risk item in the phase.

Two layers are tested, because either alone is insufficient: the query condition that
filters list views and reports, and the row-level check that stops a document being opened
by its direct URL.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import permissions
from a3_sola.registry import all_permission_doctypes
from a3_sola.tests.fixtures import default_company, make_company, make_consumer


def make_user(email, company, roles=("Solar Sales Executive",)):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		)
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
	frappe.db.delete("User Permission", {"user": email, "allow": "Company"})
	frappe.get_doc(
		{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": company}
	).insert(ignore_permissions=True)
	return email


class TestRegistryGuard(FrappeTestCase):
	def test_every_registered_doctype_has_a_permission_hook(self):
		"""The guard that stops a doctype shipping without tenant isolation.

		Phases 2 to 8 add doctypes to this same app. If this test fails, a doctype has been
		registered without isolation - fix the registry, never weaken this test.
		"""
		hooks = frappe.get_hooks("permission_query_conditions") or {}
		row_hooks = frappe.get_hooks("has_permission") or {}
		for doctype in all_permission_doctypes():
			self.assertIn(doctype, hooks, f"{doctype} has no permission_query_conditions hook")
			self.assertIn(doctype, row_hooks, f"{doctype} has no has_permission hook")

	def test_every_registered_doctype_actually_has_a_company_field(self):
		for doctype in all_permission_doctypes():
			self.assertTrue(
				frappe.get_meta(doctype).has_field("company"),
				f"{doctype} is registered for isolation but has no company field",
			)


class TestCompanyIsolation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company_a = default_company()
		cls.company_b = make_company("Solar Tenant B", "STB")  # seeds its own masters
		frappe.db.commit()

	def setUp(self):
		self.user_a = make_user("tenant.a@example.com", self.company_a)
		self.consumer_a = make_consumer(company=self.company_a, consumer_name="Consumer A")
		self.consumer_b = make_consumer(company=self.company_b, consumer_name="Consumer B")
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_query_conditions_restrict_to_permitted_companies(self):
		condition = permissions.build_query_conditions(self.user_a, "Solar Consumer")
		self.assertIn(self.company_a, condition)
		self.assertNotIn(self.company_b, condition)

	def test_list_view_returns_only_own_company(self):
		frappe.set_user(self.user_a)
		names = frappe.get_list("Solar Consumer", pluck="name", ignore_permissions=False)
		self.assertIn(self.consumer_a.name, names)
		self.assertNotIn(self.consumer_b.name, names)

	def test_direct_document_access_is_denied(self):
		"""The layer the query condition does not cover."""
		frappe.set_user(self.user_a)
		doc_b = frappe.get_doc("Solar Consumer", self.consumer_b.name)
		self.assertFalse(permissions.has_company_permission(doc=doc_b, ptype="read", user=self.user_a))
		doc_a = frappe.get_doc("Solar Consumer", self.consumer_a.name)
		self.assertTrue(permissions.has_company_permission(doc=doc_a, ptype="read", user=self.user_a))

	def test_cross_company_link_is_rejected_and_names_the_link(self):
		"""A Site Survey in Company A must never link a Solar Consumer in Company B."""
		with self.assertRaises(frappe.ValidationError) as ctx:
			frappe.get_doc(
				{
					"doctype": "Site Survey",
					"company": self.company_a,
					"solar_consumer": self.consumer_b.name,
					"survey_date": frappe.utils.today(),
					"feasibility_status": "Feasible",
				}
			).insert(ignore_permissions=True)
		message = str(ctx.exception)
		self.assertIn(self.consumer_b.name, message)
		self.assertIn(self.company_b, message)

	def test_administrator_is_unrestricted(self):
		self.assertEqual(permissions.build_query_conditions("Administrator", "Solar Consumer"), "")
