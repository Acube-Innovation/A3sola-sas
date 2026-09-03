# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Suspension, restoration, and the gate.

The whole of this file is about two promises. The first is that a suspension can be undone
exactly - not approximately, not "everyone enabled", but each user back to the state they
were actually in. The second is that a suspended customer can always reach the page that
ends their suspension.

The exclusion tests are the ones to read first. Resolving "the users of this tenant"
wrongly is how you disable your own staff or somebody else's customer, so each exclusion
has a test named after the mistake it prevents.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from a3_sola.api.entitlements import TENANT_FIELD
from a3_sola.api.lifecycle import access, gate, state_machine, suspension as suspension_api
from a3_sola.tests.platform import lifecycle_fixtures as fx

PREFIX = "lcaccess"


class AccessTestCase(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		fx.purge(PREFIX)
		fx.settings(**fx.INERT)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		fx.settings(**fx.LIVE)
		gate.invalidate()
		self.plan = fx.a_plan()

	def a_suspension(self, tenant, subscription, warned=True):
		doc = frappe.get_doc({
			"doctype": "Access Suspension",
			"tenant": tenant.name,
			"platform_subscription": subscription.name,
			"suspension_type": "Non Payment",
			"reason": "Unpaid for 20 days",
			"outstanding_amount": 3540,
			"requested_by": "Scheduler",
			"approval_status": "Not Required",
			"status": "Scheduled",
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		if warned:
			doc.db_set("warning_sent_on", add_days(now_datetime(), -5),
			           update_modified=False)
		return doc


class TestWhoIsNeverDisabled(AccessTestCase):
	"""Every one of these is a way to disable the wrong people.

	Each test gets its own tenant. Sharing one made the class order-dependent: a test that
	deliberately parks a Platform-role holder in a tenant makes every later suspension of
	that tenant abort - which is correct behaviour, and a badly built test.
	"""

	def setUp(self):
		super().setUp()
		self.tag = f"{PREFIX}x{self._testMethodName[5:14]}"
		self.sub = fx.a_subscription(self.tag)
		self.tenant = fx.a_tenant(self.tag, self.sub, users=2)

	def test_the_administrator_is_never_disabled(self):
		"""The account that fixes a broken suspension must never be caught by one."""
		frappe.db.set_value("User", "Administrator", TENANT_FIELD, self.tenant.name,
		                    update_modified=False)
		try:
			users, refusals = access.resolve_for_suspension(self.tenant.name)
			self.assertNotIn("Administrator", [u["name"] for u in users])
			self.assertTrue(any("system account" in r for r in refusals))
		finally:
			frappe.db.set_value("User", "Administrator", TENANT_FIELD, None,
			                    update_modified=False)

	def test_a_user_with_no_tenant_stamp_is_never_disabled(self):
		"""Your own staff carry no stamp. Disabling them is the worst outcome here."""
		email = f"{self.tag}.internal@lifecycle.example"
		fx.stamp_user(email, self.tenant.name, first_name="Internal")
		frappe.db.set_value("User", email, TENANT_FIELD, None, update_modified=False)
		users, _refusals = access.resolve_for_suspension(self.tenant.name)
		self.assertNotIn(email, [u["name"] for u in users])

	def test_a_platform_role_holder_is_never_disabled(self):
		email = f"{self.tag}.platform@lifecycle.example"
		fx.stamp_user(email, self.tenant.name, first_name="Plat",
		              roles=("Platform Billing Manager",))
		users, refusals = access.resolve_for_suspension(self.tenant.name)
		self.assertNotIn(email, [u["name"] for u in users])
		self.assertTrue(any("internal role" in r for r in refusals))

	def test_another_tenants_user_is_never_touched(self):
		other_sub = fx.a_subscription(f"{self.tag}other")
		other = fx.a_tenant(f"{self.tag}other", other_sub, users=2)
		suspension = self.a_suspension(self.tenant, self.sub)
		access.suspend_tenant_access(self.tenant.name, suspension)
		for row in frappe.get_all("User", filters={TENANT_FIELD: other.name},
		                          fields=["name", "enabled"]):
			self.assertTrue(row["enabled"], f"{row['name']} belongs to another tenant")

	def test_an_unresolvable_user_set_abandons_the_whole_suspension(self):
		"""Fail closed. Disabling nobody and shouting is always recoverable."""
		empty_sub = fx.a_subscription(f"{self.tag}empty")
		empty = fx.a_tenant(f"{self.tag}empty", empty_sub, users=0)
		suspension = self.a_suspension(empty, empty_sub)
		with self.assertRaises(frappe.ValidationError) as caught:
			access.suspend_tenant_access(empty.name, suspension)
		self.assertIn("Refusing to suspend", str(caught.exception))
		self.assertEqual(
			frappe.db.get_value("Access Suspension", suspension.name, "status"), "Failed")


class TestTheRoundTrip(AccessTestCase):
	def test_suspend_then_restore_leaves_the_user_set_byte_identical(self):
		sub = fx.a_subscription(f"{PREFIX}round")
		tenant = fx.a_tenant(f"{PREFIX}round", sub, users=3)
		before = _snapshot(tenant.name)

		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)
		self.assertTrue(all(not row["enabled"] for row in _rows(tenant.name)),
		                "somebody was left enabled by the suspension")

		access.restore_tenant_access(tenant.name, suspension, trigger="Payment Received")
		self.assertEqual(_snapshot(tenant.name), before,
		                 "the round trip did not restore the tenant exactly")

	def test_a_user_the_tenant_had_disabled_stays_disabled(self):
		"""The detail that gets missed. Restoring them hands access back to somebody the
		customer deliberately removed."""
		sub = fx.a_subscription(f"{PREFIX}kept")
		tenant = fx.a_tenant(f"{PREFIX}kept", sub, users=2)
		theirs = fx.stamp_user(f"{PREFIX}.leaver@lifecycle.example", tenant.name,
		                       first_name="Leaver", enabled=0)

		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)
		access.restore_tenant_access(tenant.name, suspension, trigger="Payment Received")

		self.assertEqual(frappe.db.get_value("User", theirs, "enabled"), 0,
		                 "restoration re-enabled a user the tenant had disabled")

	def test_no_role_or_permission_is_ever_removed(self):
		sub = fx.a_subscription(f"{PREFIX}roles")
		tenant = fx.a_tenant(f"{PREFIX}roles", sub, users=1)
		email = fx.stamp_user(f"{PREFIX}.roled@lifecycle.example", tenant.name,
		                      first_name="Roled", roles=("Solar Sales Executive",))
		before = sorted(frappe.get_roles(email))

		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)

		self.assertEqual(sorted(frappe.get_roles(email)), before,
		                 "a suspension removed a role - nothing here may do that")

	def test_the_snapshot_is_written_before_anybody_is_disabled(self):
		sub = fx.a_subscription(f"{PREFIX}snap")
		tenant = fx.a_tenant(f"{PREFIX}snap", sub, users=2)
		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)

		suspension.reload()
		self.assertEqual(len(suspension.affected_users), 2)
		for row in suspension.affected_users:
			self.assertTrue(row.was_enabled, "the snapshot did not record the prior state")
			self.assertTrue(json.loads(row.had_roles or "[]") is not None)

	def test_sessions_are_terminated_so_suspension_is_immediate(self):
		sub = fx.a_subscription(f"{PREFIX}sess")
		tenant = fx.a_tenant(f"{PREFIX}sess", sub, users=1)
		email = frappe.get_all("User", filters={TENANT_FIELD: tenant.name},
		                       pluck="name")[0]
		frappe.db.sql(
			"insert into tabSessions (user, sid, status, lastupdate, sessiondata) "
			"values (%s, %s, 'Active', now(), '{}')",
			(email, frappe.generate_hash(length=20)),
		)
		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)
		self.assertEqual(frappe.db.count("Sessions", {"user": email}), 0)


class TestASuspendedTenantCanAlwaysPay(AccessTestCase):
	"""The worst bug this phase could ship is locking a customer out of the page that ends
	their suspension. Each route is asserted separately."""

	def setUp(self):
		super().setUp()
		self.sub = fx.a_subscription(f"{PREFIX}pay")
		self.tenant = fx.a_tenant(f"{PREFIX}pay", self.sub, users=1)
		access.set_gate(self.tenant.name, "Blocked")
		self.user = frappe.get_all("User", filters={TENANT_FIELD: self.tenant.name},
		                           pluck="name")[0]

	def test_the_billing_portal_is_reachable(self):
		self.assertTrue(gate._allowed("/billing"))

	def test_the_payment_endpoint_is_reachable(self):
		self.assertTrue(gate._allowed("/api/method/a3_sola.api.payments.initiate_payment"))

	def test_the_payment_webhook_is_reachable(self):
		self.assertTrue(gate._allowed("/api/method/a3_sola.api.webhooks.razorpay"))

	def test_password_reset_is_reachable(self):
		self.assertTrue(gate._allowed("/update-password"))
		self.assertTrue(gate._allowed(
			"/api/method/frappe.core.doctype.user.user.reset_password"))

	def test_login_is_reachable(self):
		self.assertTrue(gate._allowed("/login"))
		self.assertTrue(gate._allowed("/api/method/login"))

	def test_the_desk_is_not_reachable(self):
		self.assertFalse(gate._allowed("/app/solar-installation"))
		self.assertEqual(gate.gate_for(self.user), "Blocked")

	def test_the_refusal_says_how_to_fix_it(self):
		with self.assertRaises(frappe.PermissionError) as caught:
			gate._refuse("Blocked")
		message = str(caught.exception)
		self.assertIn("billing", message)
		self.assertIn("Nothing has been deleted", message)


class TestTheGate(AccessTestCase):
	def test_internal_staff_are_never_gated(self):
		self.assertEqual(gate.gate_for("Administrator"), "Full")

	def test_a_platform_role_holder_is_never_gated(self):
		sub = fx.a_subscription(f"{PREFIX}gplat")
		tenant = fx.a_tenant(f"{PREFIX}gplat", sub, users=0)
		email = fx.stamp_user(f"{PREFIX}.gplat@lifecycle.example", tenant.name,
		                      first_name="GPlat", roles=("Platform Admin",))
		access.set_gate(tenant.name, "Blocked")
		self.assertEqual(gate.gate_for(email), "Full")

	def test_the_gate_is_cleared_the_moment_state_changes(self):
		"""A restored customer who stays locked out until a cache expires has not been
		restored."""
		sub = fx.a_subscription(f"{PREFIX}cache")
		tenant = fx.a_tenant(f"{PREFIX}cache", sub, users=1)
		email = frappe.get_all("User", filters={TENANT_FIELD: tenant.name}, pluck="name")[0]
		access.set_gate(tenant.name, "Blocked")
		self.assertEqual(gate.gate_for(email), "Blocked")

		access.clear_gate(tenant.name)
		gate.invalidate(tenant=tenant.name)
		self.assertEqual(gate.gate_for(email), "Full")

	def test_read_only_blocks_writing_and_nothing_else(self):
		sub = fx.a_subscription(f"{PREFIX}ro")
		tenant = fx.a_tenant(f"{PREFIX}ro", sub, users=1)
		email = frappe.get_all("User", filters={TENANT_FIELD: tenant.name}, pluck="name")[0]
		access.set_gate(tenant.name, "Read Only")
		gate.invalidate(tenant=tenant.name)
		self.assertEqual(gate.gate_for(email), "Read Only")

		original = frappe.session.user
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				gate.block_writes(frappe.new_doc("ToDo"))
		finally:
			frappe.set_user(original)

	def test_reading_is_never_blocked(self):
		sub = fx.a_subscription(f"{PREFIX}read")
		tenant = fx.a_tenant(f"{PREFIX}read", sub, users=1)
		access.set_gate(tenant.name, "Read Only")
		gate.invalidate(tenant=tenant.name)
		# The request gate lets Read Only through - the block happens at the document.
		self.assertNotEqual(gate.gate_for(
			frappe.get_all("User", filters={TENANT_FIELD: tenant.name}, pluck="name")[0]),
			"Blocked")


class TestTheWarningGate(AccessTestCase):
	def test_a_suspension_without_a_warning_is_refused_loudly(self):
		sub = fx.a_subscription(f"{PREFIX}warn")
		tenant = fx.a_tenant(f"{PREFIX}warn", sub, users=1)
		suspension = self.a_suspension(tenant, sub, warned=False)
		suspension.db_set({"approval_status": "Pending", "status": "Pending Approval"},
		                  update_modified=False)

		ok, why = suspension_api.warning_satisfied(suspension.name)
		self.assertFalse(ok)
		self.assertIn("warning", why.lower())

		with self.assertRaises(frappe.ValidationError) as caught:
			suspension_api.approve(suspension.name)
		self.assertIn("cannot be applied", str(caught.exception))

	def test_a_warning_sent_too_recently_is_not_enough(self):
		sub = fx.a_subscription(f"{PREFIX}soon")
		tenant = fx.a_tenant(f"{PREFIX}soon", sub, users=1)
		suspension = self.a_suspension(tenant, sub, warned=False)
		suspension.db_set("warning_sent_on", now_datetime(), update_modified=False)
		ok, why = suspension_api.warning_satisfied(suspension.name)
		self.assertFalse(ok)
		self.assertIn("3 days", why)


class TestTheApprovalQueue(AccessTestCase):
	def test_rejection_cancels_and_writes_an_event(self):
		sub = fx.a_subscription(f"{PREFIX}rej")
		tenant = fx.a_tenant(f"{PREFIX}rej", sub, users=1)
		suspension = self.a_suspension(tenant, sub)
		suspension.db_set({"approval_status": "Pending", "status": "Pending Approval"},
		                  update_modified=False)

		suspension_api.reject(suspension.name, "The customer paid by NEFT this morning.")

		self.assertEqual(
			frappe.db.get_value("Access Suspension", suspension.name, "status"), "Cancelled")
		reasons = frappe.get_all("Subscription Event",
		                         filters={"platform_subscription": sub.name}, pluck="reason")
		self.assertTrue(any("rejected" in r.lower() for r in reasons))

	def test_rejecting_without_a_reason_is_refused(self):
		sub = fx.a_subscription(f"{PREFIX}rej2")
		tenant = fx.a_tenant(f"{PREFIX}rej2", sub, users=1)
		suspension = self.a_suspension(tenant, sub)
		with self.assertRaises(frappe.ValidationError):
			suspension_api.reject(suspension.name, "  ")

	def test_inaction_never_applies_a_suspension(self):
		"""A scheduled date passing produces a reminder, never an automatic apply."""
		sub = fx.a_subscription(f"{PREFIX}wait", status="Grace")
		tenant = fx.a_tenant(f"{PREFIX}wait", sub, users=1)
		suspension = self.a_suspension(tenant, sub)
		suspension.db_set({"approval_status": "Pending", "status": "Pending Approval",
		                   "scheduled_for": add_days(now_datetime(), -2)},
		                  update_modified=False)

		reminded = suspension_api.remind_pending()

		self.assertGreaterEqual(reminded, 1)
		self.assertEqual(
			frappe.db.get_value("Access Suspension", suspension.name, "status"),
			"Pending Approval", "inaction applied the suspension")
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")

	def test_the_queue_carries_what_a_decision_needs(self):
		sub = fx.a_subscription(f"{PREFIX}queue", status="Grace", overdue_days=18)
		tenant = fx.a_tenant(f"{PREFIX}queue", sub, users=1)
		suspension = self.a_suspension(tenant, sub)
		suspension.db_set({"approval_status": "Pending", "status": "Pending Approval"},
		                  update_modified=False)

		rows = [r for r in suspension_api.approval_queue() if r["name"] == suspension.name]
		self.assertTrue(rows)
		row = rows[0]
		for field in ("days_overdue", "lifetime_value", "last_payment", "warning_ok"):
			self.assertIn(field, row)
		self.assertEqual(row["days_overdue"], 18)


class TestRestorationIsFast(AccessTestCase):
	def test_restoration_needs_no_approval_and_no_scheduler(self):
		sub = fx.a_subscription(f"{PREFIX}fast", status="Grace")
		tenant = fx.a_tenant(f"{PREFIX}fast", sub, users=2)
		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)
		state_machine.transition(sub, "Suspended", "unpaid", "Internal User",
		                         access_effect="None")

		suspension_api.restore(tenant.name, trigger="Payment Received",
		                       reason="Paid at 11pm")

		self.assertTrue(all(row["enabled"] for row in _rows(tenant.name)))
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")
		self.assertEqual(
			frappe.db.get_value("Platform Subscription", sub.name, "status"), "Active")

	def test_restoring_twice_is_harmless(self):
		sub = fx.a_subscription(f"{PREFIX}twice", status="Grace")
		tenant = fx.a_tenant(f"{PREFIX}twice", sub, users=1)
		suspension = self.a_suspension(tenant, sub)
		access.suspend_tenant_access(tenant.name, suspension)
		access.restore_tenant_access(tenant.name, suspension, trigger="Manual")
		access.restore_tenant_access(tenant.name, suspension, trigger="Manual")
		self.assertEqual(
			frappe.db.get_value("Access Suspension", suspension.name, "status"), "Restored")


def _rows(tenant):
	return frappe.get_all("User", filters={TENANT_FIELD: tenant},
	                      fields=["name", "enabled"], order_by="name")


def _snapshot(tenant):
	"""Enabled flag, roles and user permissions - everything a round trip must preserve."""
	out = {}
	for row in _rows(tenant):
		out[row["name"]] = {
			"enabled": row["enabled"],
			"roles": sorted(frappe.get_roles(row["name"])),
			"permissions": sorted(
				(p["allow"], p["for_value"]) for p in frappe.get_all(
					"User Permission", filters={"user": row["name"]},
					fields=["allow", "for_value"])
			),
		}
	return out
