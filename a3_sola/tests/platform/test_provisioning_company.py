# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The workspace a tenant gets: company, structures, masters and entitlements.

The hostile-name tests are the ones worth reading. An organisation name is free text from
a stranger on the internet, and it ends up next to an ERPNext company abbreviation, a
chart of accounts, a set of warehouse names and a naming series. What is proved here is
that none of those receive the string itself - only something derived from it by an
allowlist.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint

from a3_sola.api.provisioning import identifiers, orchestrator
from a3_sola.api.provisioning.strategies.multi_company import _free_company_name
from a3_sola.tests.platform.test_provisioning_core import ProvisioningTestCase

HOSTILE = (
	"'; DROP TABLE `tabUser`; -- <script>alert('x')</script> ../../etc/passwd "
	"Ενέργεια സൗരോർജ്ജം " + "A" * 200
)


class CompanyProvisioningTestCase(ProvisioningTestCase):
	def provision(self, **kwargs):
		_doc, order = self.paid_signup(**kwargs)
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		job = frappe.get_doc("Provisioning Job", job_name)
		self.remember(job.tenant)
		tenant = frappe.get_doc("Tenant", job.tenant) if job.tenant else None
		return job, tenant


class TestCompanyCreation(CompanyProvisioningTestCase):
	def test_the_company_carries_the_right_currency_country_and_back_link(self):
		_job, tenant = self.provision()
		self.assertTrue(tenant.company)
		company = frappe.get_doc("Company", tenant.company)
		self.assertEqual(company.default_currency, "INR")
		self.assertEqual(company.country, "India")
		self.assertEqual(
			frappe.db.get_value("Company", company.name, "a3_sola_tenant"),
			tenant.name,
			"the company does not point back at its tenant",
		)

	def test_the_abbreviation_is_derived_and_free(self):
		_job, tenant = self.provision()
		abbr = frappe.db.get_value("Company", tenant.company, "abbr")
		self.assertRegex(abbr, r"^[A-Z0-9]+$")
		self.assertEqual(
			frappe.db.count("Company", {"abbr": abbr}), 1, "two companies share an abbreviation"
		)

	def test_a_hostile_name_is_defused_before_it_reaches_a_company(self):
		"""Phase 4 refuses this at signup, but derivation must be safe on its own.

		Relying on the signup validator would mean the company layer is only safe as long
		as nobody ever adds a second way to create a tenant.
		"""
		name = _free_company_name(HOSTILE)
		for bad in ("'", '"', "<", ">", "/", "\\", ";", "`"):
			self.assertNotIn(bad, name, f"{bad!r} survived into the company name")
		self.assertLessEqual(len(name), 100)
		code = identifiers.generate_code(HOSTILE)
		identifiers.validate_code(code)
		self.assertRegex(code, r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
		self.assertRegex(identifiers.abbreviation_for(code), r"^[A-Z0-9]+$")

	def test_an_awkward_but_legal_name_provisions_cleanly(self):
		"""The names real Indian companies actually have."""
		_job, tenant = self.provision(org="M/s Sūrya Energy & Co. (Kerala)")
		company = frappe.get_doc("Company", tenant.company)
		for bad in ("/", "&", "'", '"'):
			if bad == "&":
				continue  # legal in a company name, illegal only in a report module path
			self.assertNotIn(bad, company.name)
		self.assertRegex(tenant.tenant_code, r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

	def test_a_company_name_collision_is_disambiguated(self):
		base = f"Collide EPC {frappe.generate_hash(length=5)}"
		frappe.get_doc(
			{"doctype": "Company", "company_name": base, "abbr": f"C{frappe.generate_hash(length=3).upper()}",
			 "default_currency": "INR", "country": "India"}
		).insert(ignore_permissions=True)
		second = _free_company_name(base)
		self.assertNotEqual(second, base)
		self.assertIn(base[:20], second)


class TestStructures(CompanyProvisioningTestCase):
	def test_cost_centres_and_warehouses_are_created(self):
		_job, tenant = self.provision()
		company = tenant.company
		for label in ("Sales", "Projects", "Service", "Administration"):
			self.assertTrue(
				frappe.db.exists("Cost Center", {"cost_center_name": label, "company": company}),
				f"cost centre {label} missing",
			)
		for label in ("Main Store", "Site Store", "Service Van Stock", "Scrap Store"):
			self.assertTrue(
				frappe.db.exists("Warehouse", {"warehouse_name": label, "company": company}),
				f"warehouse {label} missing",
			)

	def test_the_company_gets_a_default_cost_centre(self):
		"""Without one, every Profit and Loss posting fails at submit."""
		_job, tenant = self.provision()
		self.assertTrue(frappe.db.get_value("Company", tenant.company, "cost_center"))

	def test_the_operations_settings_point_at_real_warehouses(self):
		"""Otherwise the tenant's first work order fails on a field they have never seen."""
		self.provision()
		source = frappe.db.get_single_value("A3 Sola Settings", "default_source_warehouse")
		site_group = frappe.db.get_single_value("A3 Sola Settings", "site_warehouse_group")
		self.assertTrue(source, "default_source_warehouse was never written back")
		self.assertTrue(site_group, "site_warehouse_group was never written back")
		self.assertTrue(frappe.db.exists("Warehouse", source))
		self.assertTrue(frappe.db.exists("Warehouse", site_group))

	def test_the_solar_item_groups_and_uoms_exist(self):
		self.provision()
		for label in ("Solar Packages", "Modules", "Inverters", "Meters"):
			self.assertTrue(frappe.db.exists("Item Group", {"item_group_name": label}))
		for label in ("kW", "kWp", "kWh"):
			self.assertTrue(frappe.db.exists("UOM", {"uom_name": label}))


class TestSeededMasters(CompanyProvisioningTestCase):
	def test_the_tenant_can_start_using_phases_one_to_three_immediately(self):
		"""The point of the seeding step: a tenant that cannot quote is not provisioned."""
		_job, tenant = self.provision()
		company = tenant.company
		required = (
			("DISCOM", "no distribution company"),
			("Roof Type", "no roof types, so no survey"),
			("Subsidy Scheme", "no subsidy scheme, so no eligibility check"),
			("Electricity Tariff", "no tariff, so no savings calculation"),
			("Solar Package", "no packages, so nothing to quote"),
			("Installation Stage Template", "no stage chain, so Phase 2 cannot run"),
			("Document Checklist Template", "no checklists"),
			("Component Make", "no makes, so no warranty terms"),
		)
		for doctype, why in required:
			self.assertTrue(
				frappe.db.exists(doctype, {"company": company}),
				f"{tenant.tenant_code} has {why}",
			)

	def test_every_seeded_master_carries_the_new_company(self):
		_job, tenant = self.provision()
		company = tenant.company
		for doctype in ("DISCOM", "Roof Type", "Solar Package", "Electricity Tariff"):
			rows = frappe.get_all(doctype, filters={"company": company}, pluck="name")
			self.assertTrue(rows, f"{doctype} seeded nothing for {company}")
			for name in rows:
				self.assertEqual(frappe.db.get_value(doctype, name, "company"), company)

	def test_the_account_mappings_are_created_empty(self):
		"""A guessed mapping posts money to the wrong ledger. An empty one merely waits."""
		_job, tenant = self.provision()
		row = frappe.db.get_value(
			"Solar Company Account Mapping",
			{"parenttype": "A3 Sola Settings", "company": tenant.company},
			["name", "subsidy_receivable_account", "om_expense_account", "write_off_account"],
			as_dict=True,
		)
		self.assertTrue(row, "no account mapping row was scaffolded")
		self.assertIsNone(row.subsidy_receivable_account)
		self.assertIsNone(row.om_expense_account)
		self.assertIsNone(row.write_off_account)

	def test_the_gst_valuation_rule_is_seeded_inactive(self):
		"""It is the CA's call, not ours."""
		_job, tenant = self.provision()
		rule = frappe.db.get_value(
			"Solar GST Valuation Rule", {"company": tenant.company}, ["name", "is_active"],
			as_dict=True,
		)
		if rule:
			self.assertFalse(cint(rule.is_active), "the GST rule was seeded active")

	def test_a_missing_mandatory_blueprint_item_fails_the_step(self):
		from a3_sola.api.provisioning.strategies import multi_company

		original = multi_company._verify_blueprint_completeness
		multi_company._verify_blueprint_completeness = lambda ctx, company: ["Fake DocType (item 1)"]
		try:
			job, _tenant = self.provision(auto_provision=False)
		finally:
			multi_company._verify_blueprint_completeness = original
		self.assertIn(job.status, ("Failed", "Rolled Back"))
		self.assertIn("Fake DocType", job.failure_summary or "")


class TestEntitlementsApplied(CompanyProvisioningTestCase):
	def test_the_quota_comes_from_the_snapshot(self):
		_job, tenant = self.provision()
		plan = frappe.get_cached_doc("Subscription Plan", tenant.subscription_plan)
		self.assertEqual(cint(tenant.included_users), cint(plan.included_users))
		self.assertEqual(
			cint(tenant.user_quota), cint(tenant.included_users) + cint(tenant.additional_users)
		)

	def test_the_enabled_modules_are_snapshotted_onto_the_tenant(self):
		_job, tenant = self.provision()
		plan = frappe.get_cached_doc("Subscription Plan", tenant.subscription_plan)
		expected = {r.module_name for r in plan.enabled_modules if cint(r.is_enabled)}
		actual = {r.module_name for r in tenant.enabled_modules if cint(r.is_enabled)}
		self.assertEqual(actual, expected)

	def test_seats_available_is_computed_after_the_admin_is_created(self):
		_job, tenant = self.provision()
		tenant.reload()
		self.assertEqual(cint(tenant.active_users), 1)
		self.assertEqual(cint(tenant.seats_available), cint(tenant.user_quota) - 1)


class TestRollbackRefusesOnRealData(CompanyProvisioningTestCase):
	def test_teardown_refuses_when_the_company_has_a_transaction(self):
		"""Rollback never removes a company that has started trading."""
		from a3_sola.api.provisioning.context import ProvisioningContext
		from a3_sola.api.provisioning.strategies.multi_company import (
			MultiCompanyStrategy,
			_refuse_if_company_has_data,
		)

		_job, tenant = self.provision()
		company = tenant.company
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": frappe.utils.today(),
				"accounts": [],
			}
		)
		entry.flags.ignore_permissions = True
		entry.flags.ignore_mandatory = True
		entry.flags.ignore_validate = True
		entry.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			_refuse_if_company_has_data(company)
		self.assertTrue(frappe.db.exists("Company", company))


class TestNoCompanyIsEverDeleted(FrappeTestCase):
	def test_no_code_path_force_deletes_a_company(self):
		"""Grepped rather than reasoned about, because this is the one that ends a business."""
		import os

		base = frappe.get_app_path("a3_sola")
		offenders = []
		for root, dirs, files in os.walk(base):
			dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests")]
			for filename in files:
				if not filename.endswith(".py"):
					continue
				path = os.path.join(root, filename)
				with open(path) as handle:
					for number, line in enumerate(handle, start=1):
						if 'delete_doc("Company"' not in line:
							continue
						if "force=True" in line:
							offenders.append(f"{path}:{number}")
		self.assertEqual(
			offenders, [], f"a code path force-deletes a Company: {offenders}"
		)
