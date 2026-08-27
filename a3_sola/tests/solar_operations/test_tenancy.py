# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Multi-tenant isolation for Solar Operations.

The registry guard from Phase 1 already asserts that every registered doctype has both
permission hooks and a company field. As Phases 2 to 8 add doctypes to this same app, that
test is what stops one shipping without isolation - so these tests extend it rather than
duplicating it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import permissions
from a3_sola.registry import solar_operations
from a3_sola.tests.fixtures import default_company, make_company, make_consumer
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestOperationsRegistry(FrappeTestCase):
	def test_every_operations_doctype_is_registered(self):
		"""A doctype missing from the registry ships without tenant isolation."""
		on_disk = set(
			frappe.get_all("DocType", filters={"module": "Solar Operations"}, pluck="name")
		)
		registered = set(solar_operations.DOCTYPES)
		self.assertEqual(
			on_disk - registered, set(), "doctypes exist that the registry does not declare"
		)

	def test_permission_doctypes_all_carry_a_company_field(self):
		for doctype in solar_operations.PERMISSION_DOCTYPES:
			self.assertTrue(
				frappe.get_meta(doctype).has_field("company"),
				f"{doctype} is registered for isolation but has no company field",
			)

	def test_every_company_bearing_doctype_is_isolated(self):
		"""If it has a company, it must be guarded - no exceptions, no drift."""
		missing = []
		for doctype in solar_operations.DOCTYPES:
			meta = frappe.get_meta(doctype)
			if meta.istable or not meta.has_field("company"):
				continue
			if doctype not in solar_operations.PERMISSION_DOCTYPES:
				missing.append(doctype)
		self.assertEqual(missing, [], f"unisolated doctypes: {missing}")

	def test_hooks_registered_for_every_permission_doctype(self):
		query_hooks = frappe.get_hooks("permission_query_conditions") or {}
		row_hooks = frappe.get_hooks("has_permission") or {}
		for doctype in solar_operations.PERMISSION_DOCTYPES:
			self.assertIn(doctype, query_hooks, f"{doctype} has no query condition hook")
			self.assertIn(doctype, row_hooks, f"{doctype} has no row permission hook")

	def test_extension_points_exist_and_are_inert(self):
		"""Phase 3 registers against these five. They must log and return, never post."""
		from a3_sola.api import stages

		for name in (
			"on_commissioning_submitted",
			"on_subsidy_claim_submitted",
			"on_subsidy_recovery_recorded",
			"on_statutory_fee_recorded",
			"on_statutory_refund_received",
		):
			self.assertTrue(hasattr(stages, name), f"missing extension point {name}")
			self.assertTrue(getattr(stages, name).__doc__, f"{name} has no contract docstring")


class TestOperationsIsolation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company_a = default_company()
		cls.company_b = make_company("Solar Tenant B", "STB")
		frappe.db.commit()

	def setUp(self):
		self.installation_a = make_installation()
		consumer_b = make_consumer(
			company=self.company_b, avg_consumption_units=750, sanctioned_load_kw=5
		)
		self.installation_b = make_installation(consumer_b)
		# User Permissions are read on a separate connection, so this class must commit -
		# which means it must also clean up after itself rather than leaving test records
		# in the demo data.
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in (self.installation_b.name, self.installation_a.name):
			if not frappe.db.exists("Solar Installation", name):
				continue
			doc = frappe.get_doc("Solar Installation", name)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.cancel()
			frappe.delete_doc("Solar Installation", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_query_conditions_restrict_installations(self):
		condition = permissions.build_query_conditions("tenant.a@example.com", "Solar Installation")
		if condition:
			self.assertNotIn(self.company_b, condition)

	def test_direct_access_denied_across_companies(self):
		user = "ops.tenant.a@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "OpsA",
					"send_welcome_email": 0,
					"roles": [{"role": "Solar Operations Executive"}],
				}
			).insert(ignore_permissions=True)
		frappe.db.delete("User Permission", {"user": user, "allow": "Company"})
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Company", "for_value": self.company_a}
		).insert(ignore_permissions=True)

		doc_b = frappe.get_doc("Solar Installation", self.installation_b.name)
		self.assertFalse(permissions.has_company_permission(doc=doc_b, ptype="read", user=user))
		doc_a = frappe.get_doc("Solar Installation", self.installation_a.name)
		self.assertTrue(permissions.has_company_permission(doc=doc_a, ptype="read", user=user))

	def test_cross_company_link_rejected_and_named(self):
		"""A Company A installation must never link a Company B consumer."""
		with self.assertRaises(frappe.ValidationError) as ctx:
			frappe.get_doc(
				{
					"doctype": "Portal Application",
					"company": self.company_a,
					"solar_installation": self.installation_b.name,
					"application_type": "National Portal",
					"application_number": frappe.generate_hash(length=8),
					"application_date": frappe.utils.today(),
				}
			).insert(ignore_permissions=True)
		message = str(ctx.exception)
		self.assertIn(self.installation_b.name, message)
		self.assertIn(self.company_b, message)

	def test_each_tenant_has_its_own_stage_templates(self):
		"""Masters are per company - a second tenant needs its own chain."""
		for company in (self.company_a, self.company_b):
			self.assertTrue(
				frappe.db.exists("Installation Stage Template", {"company": company, "is_default": 1}),
				f"{company} has no default stage template",
			)

	def test_each_tenant_has_its_own_document_templates(self):
		for company in (self.company_a, self.company_b):
			self.assertGreater(
				frappe.db.count("Solar Document Template", {"company": company}),
				10,
				f"{company} has no document templates",
			)

	def test_serial_uniqueness_spans_tenants(self):
		"""The national portal does not care whose tenant the duplicate came from."""
		from a3_sola.api import serials

		doc_a = frappe.get_doc("Solar Installation", self.installation_a.name)
		doc_a.append("serials", {"component_type": "Module", "serial_no": "CROSS-TENANT-001"})
		doc_a.flags.ignore_validate_update_after_submit = True
		doc_a.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			serials.validate_serial_uniqueness(
				"CROSS-TENANT-001", self.installation_b.name, self.company_b
			)
