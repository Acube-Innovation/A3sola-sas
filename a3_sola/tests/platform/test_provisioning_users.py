# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Admin creation, permissions, invitations and the seat quota.

The quota tests are the load-bearing ones, and they come in two halves that are equally
important. One half proves the gate holds: the sixth user on a five-seat plan is refused
at every entry point, including the one somebody always forgets - accepting an invitation
that was sent while seats were still free.

The other half proves the gate is not a hazard. A quota check that can block the
Administrator, or a tenant's own admin account, or somebody *disabling* a user to free a
seat, turns a billing feature into an outage. Each of those has its own test here because
each of them is a plausible bug.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, cint, now_datetime

from a3_sola.api import entitlements, invitations, tenant_users
from a3_sola.api.provisioning import orchestrator
from a3_sola.tests.platform.test_provisioning_core import ProvisioningTestCase


class UserProvisioningTestCase(ProvisioningTestCase):
	#: Users made directly by the fixtures rather than by provisioning. They carry a
	#: tenant stamp, so leaving them would keep counting against a quota nobody owns.
	_extra_users = []

	@classmethod
	def tearDownClass(cls):
		for email in cls._extra_users:
			try:
				frappe.db.delete("User Permission", {"user": email})
				frappe.delete_doc("User", email, force=True, ignore_permissions=True,
				                  ignore_on_trash=True)
			except Exception:
				frappe.db.rollback()
		cls._extra_users = []
		frappe.db.commit()
		super().tearDownClass()

	def provision(self, **kwargs):
		_doc, order = self.paid_signup(**kwargs)
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		job = frappe.get_doc("Provisioning Job", job_name)
		self.remember(job.tenant)
		tenant = frappe.get_doc("Tenant", job.tenant) if job.tenant else None
		return job, tenant

	def make_tenant_user(self, tenant, email=None):
		"""A user created the way an accepted invitation creates one.

		The role matters. Frappe demotes a user with no desk-access role to a Website
		User, and a Website User consumes no seat - correctly, because a tenant's own
		customers on the Phase 3 portal are Website Users and nobody sells seats for them.
		A fixture without a role would therefore never fill the quota, and every quota test
		would pass by never reaching the limit.
		"""
		email = email or f"member{frappe.generate_hash(length=6)}@epc.example"
		user = frappe.new_doc("User")
		user.update(
			{
				"email": email,
				"first_name": "Member",
				"user_type": "System User",
				"enabled": 1,
				"send_welcome_email": 0,
				"a3_sola_tenant": tenant.name,
				"roles": [{"role": "Solar Sales Executive"}],
			}
		)
		user.flags.ignore_permissions = True
		# Frappe throttles user creation at sixty a minute site-wide. A suite that fills
		# several tenants to their quota trips it, and a throttle error looks exactly like
		# a quota error - which would make these tests pass for the wrong reason.
		was_import = frappe.flags.in_import
		frappe.flags.in_import = True
		try:
			user.insert(ignore_permissions=True)
		finally:
			frappe.flags.in_import = was_import
		self._extra_users.append(email)
		return email

	def fill_to_quota(self, tenant):
		"""Create users until exactly one seat short of the quota (the admin holds one)."""
		usage = entitlements.get_tenant_usage(tenant.name)
		created = []
		while entitlements.get_tenant_usage(tenant.name)["available_ignoring_pending"] > 0:
			created.append(self.make_tenant_user(tenant))
			if len(created) > usage["quota"] + 2:
				self.fail("the quota never filled - enforcement arithmetic is wrong")
		return created


class TestAdminUser(UserProvisioningTestCase):
	def test_the_admin_is_created_with_no_password(self):
		"""A system that can set a password is one whose backups contain passwords."""
		_job, tenant = self.provision()
		self.assertTrue(tenant.admin_user)
		auth = frappe.db.sql(
			"SELECT `password` FROM `__Auth` WHERE doctype='User' AND name=%s AND fieldname='password'",
			(tenant.admin_user,),
		)
		self.assertFalse(auth, "a password was set for the tenant administrator")

	def test_a_reset_link_is_issued_and_expires(self):
		_job, tenant = self.provision()
		link = tenant_users.password_reset_link(tenant.admin_user)
		self.assertIn("/update-password?key=", link["url"])
		self.assertGreater(link["expires_in_hours"], 0)
		self.assertTrue(frappe.db.get_value("User", tenant.admin_user, "reset_password_key"))

	def test_an_existing_email_fails_the_step_rather_than_reusing_the_account(self):
		"""One login across two tenants is a cross-tenant access bug with a friendly face."""
		email = f"taken{frappe.generate_hash(length=6)}@epc.example"
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Already", "send_welcome_email": 0}
		).insert(ignore_permissions=True)

		job, tenant = self.provision(email=email, auto_provision=False)
		self.assertEqual(job.status, "Failed Past Point of No Return")
		self.assertTrue(job.requires_manual_intervention)
		self.assertIn("already exists", (job.failure_summary or "").lower())
		if tenant:
			tenant.reload()
			self.assertEqual(tenant.status, "Provisioned with Errors")
			self.assertFalse(tenant.admin_user)

	def test_the_admin_is_stamped_with_their_tenant(self):
		_job, tenant = self.provision()
		self.assertEqual(
			frappe.db.get_value("User", tenant.admin_user, "a3_sola_tenant"), tenant.name
		)


class TestAdminPermissions(UserProvisioningTestCase):
	def test_the_company_user_permission_exists_and_is_read_back(self):
		"""Without this single record the admin sees every tenant on the instance."""
		_job, tenant = self.provision()
		self.assertTrue(
			frappe.db.exists(
				"User Permission",
				{"user": tenant.admin_user, "allow": "Company", "for_value": tenant.company},
			)
		)

	def test_the_tenant_admin_holds_no_internal_platform_role(self):
		"""The boundary between your customer and your own business data."""
		_job, tenant = self.provision()
		held = set(frappe.get_roles(tenant.admin_user))
		leaked = held & set(entitlements.INTERNAL_PLATFORM_ROLES)
		self.assertEqual(leaked, set(), f"the tenant admin holds internal roles: {leaked}")

	def test_a_starter_tenant_admin_holds_no_solar_projects_role(self):
		_job, tenant = self.provision(plan_code="starter")
		enabled = entitlements.enabled_modules(tenant.name)
		if "Solar Projects" in enabled:
			self.skipTest("this plan includes Solar Projects")
		held = set(frappe.get_roles(tenant.admin_user))
		projects_roles = set(entitlements.MODULE_ROLES["Solar Projects"])
		self.assertEqual(
			held & projects_roles, set(),
			"a Starter tenant admin holds Solar Projects roles their plan excludes",
		)

	def test_a_growth_tenant_admin_does_hold_solar_projects_roles(self):
		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "growth"}, "name")
		if not plan:
			self.skipTest("no growth plan on this site")
		_job, tenant = self.provision(plan_code="growth")
		if "Solar Projects" not in entitlements.enabled_modules(tenant.name):
			self.skipTest("the growth plan does not include Solar Projects on this site")
		held = set(frappe.get_roles(tenant.admin_user))
		self.assertTrue(held & set(entitlements.MODULE_ROLES["Solar Projects"]))

	def test_the_admin_default_company_is_their_own(self):
		_job, tenant = self.provision()
		self.assertEqual(
			frappe.defaults.get_user_default("Company", tenant.admin_user), tenant.company
		)


class TestModuleEntitlements(UserProvisioningTestCase):
	def test_apply_module_entitlements_is_idempotent(self):
		_job, tenant = self.provision()
		first = entitlements.apply_module_entitlements(tenant.name)
		second = entitlements.apply_module_entitlements(tenant.name)
		self.assertEqual(second["changed"], [], "a second run changed something")
		self.assertIsInstance(first["forbidden"], list)

	def test_it_corrects_drift(self):
		"""Somebody granting a role by hand is exactly what this repairs."""
		_job, tenant = self.provision()
		forbidden = sorted(entitlements.forbidden_roles(tenant.name))
		grantable = [r for r in forbidden if frappe.db.exists("Role", r)]
		if not grantable:
			self.skipTest("this plan forbids nothing that exists")
		role = grantable[0]
		user = frappe.get_doc("User", tenant.admin_user)
		user.append("roles", {"role": role})
		user.flags.ignore_permissions = True
		user.save(ignore_permissions=True)
		self.assertIn(role, frappe.get_roles(tenant.admin_user))

		entitlements.apply_module_entitlements(tenant.name)
		frappe.clear_cache(user=tenant.admin_user)
		self.assertNotIn(role, frappe.get_roles(tenant.admin_user))

	def test_has_module_is_true_for_internal_staff(self):
		"""Your own people are not customers of your own plans."""
		self.assertTrue(entitlements.has_module("Solar Projects", "Administrator"))


class TestSeatQuota(UserProvisioningTestCase):
	def test_the_first_user_past_the_quota_is_refused(self):
		_job, tenant = self.provision()
		self.fill_to_quota(tenant)
		usage = entitlements.get_tenant_usage(tenant.name)
		self.assertEqual(usage["available_ignoring_pending"], 0)
		with self.assertRaises(frappe.ValidationError) as caught:
			self.make_tenant_user(tenant)
		message = str(caught.exception)
		self.assertIn(str(usage["quota"]), message, "the message does not name the quota")

	def test_the_refusal_says_what_to_do_about_it(self):
		_job, tenant = self.provision()
		self.fill_to_quota(tenant)
		with self.assertRaises(frappe.ValidationError) as caught:
			self.make_tenant_user(tenant)
		message = str(caught.exception).lower()
		self.assertTrue(
			"seat" in message and ("buy" in message or "remove" in message),
			f"a customer cannot act on this message: {message}",
		)

	def test_disabling_a_user_is_never_blocked(self):
		"""A quota check that blocks somebody freeing a seat is actively harmful."""
		_job, tenant = self.provision()
		created = self.fill_to_quota(tenant)
		self.assertTrue(created)
		user = frappe.get_doc("User", created[0])
		user.enabled = 0
		user.flags.ignore_permissions = True
		user.save(ignore_permissions=True)
		self.assertEqual(cint(frappe.db.get_value("User", created[0], "enabled")), 0)

	def test_re_enabling_past_the_quota_is_blocked(self):
		_job, tenant = self.provision()
		created = self.fill_to_quota(tenant)
		frappe.db.set_value("User", created[0], "enabled", 0, update_modified=False)
		entitlements.recalculate_usage(tenant.name)
		self.make_tenant_user(tenant)  # takes the freed seat

		user = frappe.get_doc("User", created[0])
		user.enabled = 1
		user.flags.ignore_permissions = True
		with self.assertRaises(frappe.ValidationError):
			user.save(ignore_permissions=True)

	def test_the_administrator_is_never_blocked(self):
		_job, tenant = self.provision()
		self.fill_to_quota(tenant)
		administrator = frappe.get_doc("User", "Administrator")
		administrator.flags.ignore_permissions = True
		administrator.save(ignore_permissions=True)  # must not raise

	def test_a_user_with_no_tenant_stamp_is_never_blocked(self):
		"""Internal staff are not metered against anybody's plan."""
		_job, tenant = self.provision()
		self.fill_to_quota(tenant)
		email = f"staff{frappe.generate_hash(length=6)}@acube.example"
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Staff", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("User", email))

	def test_the_tenants_own_admin_is_never_blocked(self):
		"""A tenant locked out of its own admin account is a support catastrophe."""
		_job, tenant = self.provision()
		self.fill_to_quota(tenant)
		frappe.db.set_value("Tenant", tenant.name, "user_quota", 0, update_modified=False)
		try:
			admin = frappe.get_doc("User", tenant.admin_user)
			admin.flags.ignore_permissions = True
			admin.save(ignore_permissions=True)  # must not raise
		finally:
			frappe.db.set_value("Tenant", tenant.name, "user_quota", tenant.user_quota,
			                    update_modified=False)

	def test_usage_counters_track_reality(self):
		_job, tenant = self.provision()
		self.make_tenant_user(tenant)
		usage = entitlements.recalculate_usage(tenant.name)
		tenant.reload()
		self.assertEqual(cint(tenant.active_users), usage["used"])
		self.assertEqual(cint(tenant.seats_available), usage["available"])

	def test_the_nightly_job_reports_a_tenant_over_quota(self):
		_job, tenant = self.provision()
		self.make_tenant_user(tenant)
		frappe.db.set_value("Tenant", tenant.name, "user_quota", 1, update_modified=False)
		frappe.db.set_value("Tenant", tenant.name, "status", "Active", update_modified=False)
		result = entitlements.recalculate_all_usage()
		self.assertGreaterEqual(result["over_quota"], 1)


class TestInvitations(UserProvisioningTestCase):
	def test_an_invitation_gets_a_token_and_an_expiry(self):
		_job, tenant = self.provision()
		name = invitations.create_invitation(
			tenant.name, f"colleague{frappe.generate_hash(length=6)}@epc.example", silent=True
		)
		invitation = frappe.get_doc("Tenant Invitation", name)
		self.assertTrue(invitation.invitation_token)
		self.assertGreater(len(invitation.invitation_token), 32)
		self.assertTrue(invitation.token_expires_on)

	def test_a_duplicate_open_invitation_is_refused(self):
		_job, tenant = self.provision()
		dupe = f"dupe{frappe.generate_hash(length=6)}@epc.example"
		invitations.create_invitation(tenant.name, dupe, silent=True)
		with self.assertRaises(frappe.ValidationError):
			invitations.create_invitation(tenant.name, dupe, silent=True)

	def test_accepting_creates_a_confined_user(self):
		_job, tenant = self.provision()
		email = f"joiner{frappe.generate_hash(length=6)}@epc.example"
		name = invitations.create_invitation(tenant.name, email, silent=True)
		token = frappe.db.get_value("Tenant Invitation", name, "invitation_token")
		frappe.db.set_value("Tenant", tenant.name, "status", "Active", update_modified=False)

		result = invitations.accept_invitation(token)
		self.assertEqual(result["status"], "ok")
		self.assertIn("/update-password?key=", result["set_password_url"])
		self.assertEqual(frappe.db.get_value("User", email, "a3_sola_tenant"), tenant.name)
		self.assertTrue(
			frappe.db.exists(
				"User Permission",
				{"user": email, "allow": "Company", "for_value": tenant.company},
			)
		)

	def test_an_expired_token_is_refused(self):
		_job, tenant = self.provision()
		name = invitations.create_invitation(
			tenant.name, f"late{frappe.generate_hash(length=6)}@epc.example", silent=True
		)
		token = frappe.db.get_value("Tenant Invitation", name, "invitation_token")
		frappe.db.set_value(
			"Tenant Invitation", name, "token_expires_on", add_days(now_datetime(), -1),
			update_modified=False,
		)
		with self.assertRaises(frappe.ValidationError):
			invitations.accept_invitation(token)
		self.assertEqual(frappe.db.get_value("Tenant Invitation", name, "status"), "Expired")

	def test_a_token_cannot_be_reused(self):
		_job, tenant = self.provision()
		frappe.db.set_value("Tenant", tenant.name, "status", "Active", update_modified=False)
		name = invitations.create_invitation(
			tenant.name, f"once{frappe.generate_hash(length=6)}@epc.example", silent=True
		)
		token = frappe.db.get_value("Tenant Invitation", name, "invitation_token")
		invitations.accept_invitation(token)
		with self.assertRaises(frappe.ValidationError):
			invitations.accept_invitation(token)

	def test_a_revoked_token_is_dead_immediately(self):
		_job, tenant = self.provision()
		name = invitations.create_invitation(
			tenant.name, f"revoked{frappe.generate_hash(length=6)}@epc.example", silent=True
		)
		token = frappe.db.get_value("Tenant Invitation", name, "invitation_token")
		invitations.revoke(name, reason="Left the company")
		self.assertEqual(frappe.db.get_value("Tenant Invitation", name, "status"), "Revoked")
		with self.assertRaises(frappe.ValidationError):
			invitations.accept_invitation(token)

	def test_the_quota_is_rechecked_at_acceptance(self):
		"""Seats fill between sending and accepting. Checking only at send time is the bug."""
		_job, tenant = self.provision()
		frappe.db.set_value("Tenant", tenant.name, "status", "Active", update_modified=False)
		late = f"toolate{frappe.generate_hash(length=6)}@epc.example"
		name = invitations.create_invitation(tenant.name, late, silent=True)
		token = frappe.db.get_value("Tenant Invitation", name, "invitation_token")

		self.fill_to_quota(tenant)  # the seats go while the invitation is in the post
		with self.assertRaises(frappe.ValidationError):
			invitations.accept_invitation(token)
		self.assertEqual(frappe.db.get_value("Tenant Invitation", name, "status"), "Failed")
		self.assertFalse(frappe.db.exists("User", late))

	def test_an_invitation_is_refused_when_there_is_no_seat(self):
		_job, tenant = self.provision()
		self.fill_to_quota(tenant)
		with self.assertRaises(frappe.ValidationError):
			invitations.create_invitation(
				tenant.name, f"nochance{frappe.generate_hash(length=6)}@epc.example", silent=True
			)

	def test_pending_invitations_count_against_the_seats(self):
		_job, tenant = self.provision()
		before = entitlements.get_tenant_usage(tenant.name)["available"]
		invitations.create_invitation(
			tenant.name, f"pending{frappe.generate_hash(length=6)}@epc.example", silent=True
		)
		after = entitlements.get_tenant_usage(tenant.name)["available"]
		self.assertEqual(after, before - 1)

	def test_the_error_never_reveals_whether_an_address_exists(self):
		"""A guest endpoint that distinguishes the two is an enumeration oracle."""
		_job, tenant = self.provision()
		frappe.db.set_value("Tenant", tenant.name, "status", "Active", update_modified=False)
		taken = f"exists{frappe.generate_hash(length=6)}@epc.example"
		frappe.get_doc(
			{"doctype": "User", "email": taken, "first_name": "X", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		name = invitations.create_invitation(tenant.name, taken, silent=True)
		token = frappe.db.get_value("Tenant Invitation", name, "invitation_token")

		with self.assertRaises(frappe.ValidationError) as taken_error:
			invitations.accept_invitation(token)
		with self.assertRaises(frappe.ValidationError) as nonsense_error:
			invitations.accept_invitation("not-a-real-token")
		self.assertEqual(str(taken_error.exception), str(nonsense_error.exception))

	def test_stale_invitations_are_expired_by_the_nightly_job(self):
		_job, tenant = self.provision()
		name = invitations.create_invitation(
			tenant.name, f"stale{frappe.generate_hash(length=6)}@epc.example", silent=True
		)
		frappe.db.set_value(
			"Tenant Invitation", name, "token_expires_on", add_days(now_datetime(), -2),
			update_modified=False,
		)
		result = invitations.expire_stale_invitations()
		self.assertGreaterEqual(result["expired"], 1)
		self.assertEqual(frappe.db.get_value("Tenant Invitation", name, "status"), "Expired")


class TestOnboarding(UserProvisioningTestCase):
	def test_the_checklist_is_built_with_the_critical_items_first(self):
		_job, tenant = self.provision()
		tenant.reload()
		codes = [row.task_code for row in tenant.onboarding_tasks]
		self.assertIn("ACCOUNT_MAPPING", codes)
		self.assertIn("VERIFY_TARIFF", codes)
		self.assertIn("CONFIRM_GST", codes)
		critical = [row for row in tenant.onboarding_tasks if cint(row.is_critical)]
		self.assertGreaterEqual(len(critical), 3)

	def test_every_task_says_why_it_matters(self):
		_job, tenant = self.provision()
		tenant.reload()
		for row in tenant.onboarding_tasks:
			self.assertTrue(row.task_detail, f"{row.task_code} has no explanation")
			self.assertGreater(len(row.task_detail), 40)


class TestExtensionPoints(FrappeTestCase):
	"""The two seams Phase 6 left for Phase 7, now that Phase 7 has filled them.

	These used to assert the stubs still raised. What matters now is that the contracts
	they promised are actually kept - the docstrings said the funnel would stay a single
	funnel and that nothing would ever delete a customer's company, and those are the
	properties a later phase could quietly break.
	"""

	def test_add_seats_delegates_to_the_lifecycle_package(self):
		import inspect

		source = inspect.getsource(entitlements.add_seats)
		self.assertIn("a3_sola.api.lifecycle.seats", source)
		self.assertIn("phase 7", (entitlements.add_seats.__doc__ or "").lower())

	def test_set_tenant_access_state_is_still_the_single_funnel(self):
		import inspect

		from a3_sola.platform.doctype.tenant.tenant import set_tenant_access_state

		source = inspect.getsource(set_tenant_access_state)
		self.assertIn("a3_sola.api.lifecycle.handlers", source)
		self.assertIn("phase 7", (set_tenant_access_state.__doc__ or "").lower())

	def test_nothing_in_the_lifecycle_deletes_a_user_role_or_permission(self):
		"""The reversibility guarantee, checked as a property of the source rather than
		of one code path - a suspension that deleted anything could not be undone."""
		import os

		base = frappe.get_app_path("a3_sola", "api", "lifecycle")
		offenders = []
		for filename in sorted(os.listdir(base)):
			if not filename.endswith(".py"):
				continue
			with open(os.path.join(base, filename)) as handle:
				source = handle.read()
			for forbidden in ('delete_doc("User"', "delete_doc('User'",
			                  'delete_doc("Role"', "delete_doc('Role'",
			                  'delete_doc("User Permission"',
			                  'delete_doc("Role Profile"'):
				if forbidden in source:
					offenders.append(f"{filename}: {forbidden}")
		self.assertEqual(
			offenders, [],
			f"the lifecycle deletes something it could not restore: {offenders}",
		)
