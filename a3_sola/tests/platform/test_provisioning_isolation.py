# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The gating isolation step, and the properties that make it worth gating on.

Two of these tests are about the test itself rather than the product, and they are the
most important ones here. An isolation check written with `frappe.get_all` passes on an
instance with no isolation whatsoever, because `get_all` sets `ignore_permissions=True` -
it queries the database, not the permission layer. A check that always passes is worse
than no check, because it is reported as a pass.

So: one test asserts the checker uses `get_list`, and one asserts that deliberately
breaking isolation makes it fail. If the second ever stops failing, the checker has
stopped checking.
"""

import inspect

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import isolation
from a3_sola.api.provisioning import orchestrator
from a3_sola.tests.platform.test_provisioning_core import ProvisioningTestCase


class IsolationTestCase(ProvisioningTestCase):
	def provision(self, **kwargs):
		_doc, order = self.paid_signup(**kwargs)
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		job = frappe.get_doc("Provisioning Job", job_name)
		self.remember(job.tenant)
		tenant = frappe.get_doc("Tenant", job.tenant) if job.tenant else None
		return job, tenant


class TestTheCheckerActuallyChecks(FrappeTestCase):
	def test_it_queries_through_the_permission_layer(self):
		"""`get_all` ignores permissions. A check built on it proves nothing."""
		source = inspect.getsource(isolation)
		body = source.split("def _result(")[0]
		self.assertNotIn(
			"frappe.get_all(doctype", body,
			"an isolation check uses get_all, which bypasses the permission layer",
		)
		self.assertIn("frappe.get_list(", body)

	def test_it_restores_the_session_user_even_on_failure(self):
		"""Leaving the session as somebody else would be the worst possible bug here."""
		source = inspect.getsource(isolation.run_for_tenant)
		self.assertIn("finally:", source)
		self.assertIn("frappe.set_user(original_user)", source)

	def test_it_iterates_the_registry_rather_than_a_list(self):
		"""A doctype added in a later phase must be covered without anyone remembering."""
		source = inspect.getsource(isolation._check_registered_doctypes)
		self.assertIn("all_permission_doctypes", source)


class TestIsolationOnARealTenant(IsolationTestCase):
	def test_a_freshly_provisioned_tenant_passes_every_check(self):
		_job, tenant = self.provision()
		tenant.reload()
		failures = [r for r in tenant.isolation_results if r.status in ("Failed", "Error")]
		self.assertEqual(
			[f"{r.test_code}: {r.actual_result}" for r in failures], [],
			"a freshly provisioned tenant does not pass isolation",
		)
		self.assertTrue(tenant.isolation_test_passed)

	def test_it_covers_every_company_scoped_doctype_in_all_four_modules(self):
		from a3_sola.registry import all_permission_doctypes

		_job, tenant = self.provision()
		tenant.reload()
		covered = {
			r.target_doctype for r in tenant.isolation_results if r.test_code.startswith("LIST::")
		}
		expected = {
			d for d in set(all_permission_doctypes())
			if frappe.db.exists("DocType", d)
			and not frappe.get_meta(d).issingle
			and not frappe.get_meta(d).istable
		}
		self.assertEqual(expected - covered, set(), "registered doctypes went unchecked")
		self.assertGreaterEqual(len(covered), 20)

	def test_it_checks_the_platform_doctypes_that_hold_your_own_business_data(self):
		_job, tenant = self.provision()
		tenant.reload()
		checked = {
			r.target_doctype for r in tenant.isolation_results if r.test_code.startswith("PLATFORM::")
		}
		for doctype in ("Payment Order", "Subscription Signup", "Tenant", "Provisioning Job"):
			self.assertIn(doctype, checked, f"{doctype} is never checked")

	def test_a_broken_user_permission_makes_it_fail(self):
		"""The one bug this whole step exists to catch: the missing User Permission."""
		_job, tenant = self.provision()
		frappe.db.delete(
			"User Permission",
			{"user": tenant.admin_user, "allow": "Company", "for_value": tenant.company},
		)
		frappe.clear_cache(user=tenant.admin_user)
		try:
			isolation.run_for_tenant(tenant.name, blocking=False)
			tenant.reload()
			failures = [r for r in tenant.isolation_results if r.status == "Failed"]
			self.assertTrue(
				failures,
				"isolation passed with the company User Permission deleted - the check is "
				"not checking anything",
			)
			self.assertFalse(tenant.isolation_test_passed)
			self.assertEqual(
				frappe.db.get_value("Tenant", tenant.name, "status"), "Provisioned with Errors"
			)
		finally:
			from a3_sola.api import tenant_users

			tenant_users.ensure_company_permission(tenant.admin_user, tenant.company)
			frappe.clear_cache(user=tenant.admin_user)

	def test_failure_blocks_activation(self):
		"""A tenant that might see another customer's data is never handed over."""
		from a3_sola.api import activation

		_job, tenant = self.provision()
		frappe.db.set_value("Tenant", tenant.name, "isolation_test_passed", 0,
		                    update_modified=False)
		from a3_sola.api.provisioning.context import ProvisioningContext

		subscription = frappe.get_doc("Platform Subscription", tenant.platform_subscription)
		context = ProvisioningContext(subscription)
		context.tenant = frappe.get_doc("Tenant", tenant.name)
		with self.assertRaises(frappe.ValidationError):
			activation.activate(context)

	def test_a_rerun_is_available_at_any_time(self):
		_job, tenant = self.provision()
		result = isolation.rerun(tenant.name)
		self.assertIn("checks", result["remarks"])

	def test_the_monthly_sweep_covers_active_tenants(self):
		_job, tenant = self.provision()
		frappe.db.set_value("Tenant", tenant.name, "status", "Active", update_modified=False)
		result = isolation.monthly_isolation_sweep()
		self.assertGreaterEqual(result["checked"], 1)


class TestReportsAreScoped(IsolationTestCase):
	def test_a_report_refuses_a_company_the_caller_does_not_hold(self):
		"""Raw SQL from `filters.company` was a real leak; this is the guard for it."""
		from a3_sola.api.permissions import resolve_report_company

		_job, tenant = self.provision()
		other = frappe.get_all(
			"Company", filters={"name": ["!=", tenant.company]}, pluck="name", limit=1
		)
		if not other:
			self.skipTest("only one company on this site")
		original = frappe.session.user
		frappe.set_user(tenant.admin_user)
		try:
			with self.assertRaises(frappe.PermissionError):
				resolve_report_company(other[0])
			self.assertEqual(resolve_report_company(None), tenant.company)
		finally:
			frappe.set_user(original)

	def test_every_report_with_a_company_filter_resolves_it_through_the_guard(self):
		import os

		base = frappe.get_app_path("a3_sola")
		offenders = []
		for module in ("solar_crm", "solar_operations", "solar_projects", "platform"):
			root = os.path.join(base, module, "report")
			if not os.path.isdir(root):
				continue
			for folder in sorted(os.listdir(root)):
				path = os.path.join(root, folder, folder + ".py")
				if not os.path.exists(path):
					continue
				with open(path) as handle:
					source = handle.read()
				if "filters.company" not in source:
					continue
				if "resolve_report_company" not in source:
					offenders.append(f"{module}/{folder}")
		self.assertEqual(
			offenders, [],
			f"these reports take a company filter without checking it: {offenders}",
		)
