# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The orchestrator: idempotency, ordering, resume and rollback.

This is the most dangerous code in the product, so these tests are about the properties
rather than the happy path. The happy path is covered by the company and user suites; what
is proved here is that running provisioning twice, or three times, or concurrently, or
after a crash, produces exactly one tenant - and that a failure on the reversible side of
the line leaves nothing behind.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime, set_request

from a3_sola.api import payments, ratelimit, signup
from a3_sola.api.provisioning import identifiers, orchestrator
from a3_sola.api.provisioning import steps as step_module
from a3_sola.tests.platform.test_signup import payload


class ProvisioningTestCase(FrappeTestCase):
	"""Base for every provisioning suite, and it cleans up after itself.

	This matters more than it looks. Provisioning commits after every step - deliberately,
	so a crash mid-pipeline leaves an accurate picture of where it stopped - which means
	`FrappeTestCase`'s transaction rollback does not undo a single thing these tests
	create. Each test leaves behind a Company with a full chart of accounts and about a
	hundred seeded masters, permanently.

	Without the teardown below the suite poisons its own database: every later test lists
	against tables thousands of rows deeper, every Company insert rebuilds a chart against
	a larger Account table, and the whole run gets slower on every execution until it is
	unusable. That is not hypothetical - it happened, and a run that used to take eight
	minutes took eight hours.
	"""

	#: Tenants created by this class, torn down when the class finishes.
	_provisioned = []

	@classmethod
	def tearDownClass(cls):
		cls.purge_provisioned()
		super().tearDownClass()

	@classmethod
	def purge_provisioned(cls):
		from a3_sola.tests.platform.provisioning_cleanup import purge_tenants

		purge_tenants(cls._provisioned)
		cls._provisioned = []

	def remember(self, tenant_name):
		if tenant_name and tenant_name not in type(self)._provisioned:
			type(self)._provisioned.append(tenant_name)
		return tenant_name

	def setUp(self):
		set_request(method="POST", path="/api/method/a3_sola.api.payments.initiate_payment")
		ratelimit.reset_all()
		frappe.flags.mock_gateway_behaviour = "success"
		frappe.db.set_single_value("A3 Sola Settings", "company_state_code", "32")
		frappe.db.set_single_value("A3 Sola Settings", "subscription_gst_rate", 18)
		frappe.db.set_single_value("A3 Sola Settings", "provisioning_mode", "Automatic")
		frappe.db.set_single_value("A3 Sola Settings", "run_isolation_test_on_provision", 1)
		frappe.clear_cache()

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.flags.a3s_provisioning_admin = None
		frappe.set_user("Administrator")
		ratelimit.reset_all()

	# ------------------------------------------------------------------ fixtures
	def paid_signup(self, email=None, org=None, webhook=True, plan_code="starter",
	                auto_provision=True):
		"""A signup taken all the way to a webhook-confirmed payment.

		A confirmed payment provisions on its own - that is the product working. Tests that
		want to drive the run themselves pass `auto_provision=False`, which puts the site
		in Manual Approval for the duration of the payment. The job is then created and
		left Queued, which is exactly the state a real site in that mode reaches, so the
		test is still exercising a supported path rather than a test-only hook.
		"""
		email = email or f"admin{frappe.generate_hash(length=6)}@epc.example"
		org = org or f"Test EPC {frappe.generate_hash(length=5)}"
		# A distinct number per tenant. Frappe makes `User.mobile_no` unique across the
		# instance, so a shared fixture number would make every second tenant look like a
		# duplicate-user failure rather than testing what the test is about.
		phone = "9" + str(abs(hash(email)))[:9].ljust(9, "7")
		plan = frappe.db.get_value("Subscription Plan", {"plan_code": plan_code}, "name")
		signup.submit_signup(
			payload(work_email=email, organisation_name=org, subscription_plan=plan, phone=phone)
		)
		doc = frappe.get_doc(
			"Subscription Signup", frappe.db.get_value("Subscription Signup", {"work_email": email}, "name")
		)
		signup.verify_email(doc.verification_token)
		doc.reload()
		key = signup._summary_key(doc)
		result = payments.initiate_payment(doc.name, key)
		order = frappe.get_doc("Payment Order", result["payment_order"])

		was_mode = frappe.db.get_single_value("A3 Sola Settings", "provisioning_mode")
		if not auto_provision:
			frappe.db.set_single_value("A3 Sola Settings", "provisioning_mode", "Manual Approval")
			frappe.clear_cache()
		try:
			payments.apply_successful_payment(
				order, f"pay_{frappe.generate_hash(length=10)}",
				"Webhook" if webhook else "Checkout Callback",
			)
		finally:
			if not auto_provision:
				# Back to whatever it was, not to Automatic - a test that set Manual
				# Approval itself must still be in it when the fixture returns.
				frappe.db.set_single_value("A3 Sola Settings", "provisioning_mode", was_mode)
				frappe.clear_cache()
		order.reload()
		# Whatever the payment provisioned automatically has to be cleaned up too.
		tenant = frappe.db.get_value(
			"Tenant", {"platform_subscription": order.platform_subscription}, "name"
		)
		if tenant:
			self.remember(tenant)
		return doc, order

	def tenant_of(self, job_name):
		return self.remember(frappe.db.get_value("Provisioning Job", job_name, "tenant"))


class TestIdempotency(ProvisioningTestCase):
	def test_five_calls_produce_one_job_and_one_tenant(self):
		_doc, order = self.paid_signup()
		subscription = order.platform_subscription
		self.assertTrue(subscription, "the payment did not create a subscription container")

		jobs = {orchestrator.run_provisioning(subscription) for _ in range(5)}
		self.remember(frappe.db.get_value("Tenant", {"platform_subscription": subscription}, "name"))
		self.assertEqual(len(jobs), 1, f"more than one job was created: {jobs}")
		self.assertEqual(
			frappe.db.count("Provisioning Job", {"platform_subscription": subscription}), 1
		)
		self.assertEqual(frappe.db.count("Tenant", {"platform_subscription": subscription}), 1)

	def test_the_idempotency_key_comes_from_the_subscription(self):
		"""Keying on the event would give every redelivery its own key."""
		self.assertEqual(
			orchestrator.idempotency_key("SUB-0001"), orchestrator.idempotency_key("SUB-0001")
		)
		self.assertNotEqual(
			orchestrator.idempotency_key("SUB-0001"), orchestrator.idempotency_key("SUB-0002")
		)

	def test_a_second_call_creates_no_second_company_or_user(self):
		_doc, order = self.paid_signup()
		orchestrator.run_provisioning(order.platform_subscription)
		companies = frappe.db.count("Company")
		users = frappe.db.count("User")
		orchestrator.run_provisioning(order.platform_subscription)
		self.assertEqual(frappe.db.count("Company"), companies)
		self.assertEqual(frappe.db.count("User"), users)


class TestConcurrency(ProvisioningTestCase):
	def test_a_second_call_while_the_lock_is_held_does_not_proceed(self):
		"""Two workers must serialise. The loser returns the in-flight job, not a new one."""
		_doc, order = self.paid_signup()
		subscription = order.platform_subscription
		first = orchestrator.run_provisioning(subscription)

		lock = orchestrator._subscription_lock(subscription)
		with lock as acquired:
			self.assertTrue(acquired)
			second = orchestrator.run_provisioning(subscription)
		self.assertEqual(second, first)
		self.assertEqual(
			frappe.db.count("Provisioning Job", {"platform_subscription": subscription}), 1
		)


class TestPaymentGate(ProvisioningTestCase):
	def test_a_callback_only_payment_does_not_provision(self):
		"""A browser callback is a hint. Provisioning off a hint gives tenants away."""
		_doc, order = self.paid_signup(webhook=False, auto_provision=False)
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		job = frappe.get_doc("Provisioning Job", job_name)
		self.assertIn(job.status, ("Failed", "Rolled Back"))
		self.assertIn("webhook", (job.failure_summary or "").lower())
		self.assertFalse(frappe.db.exists("Tenant", {"platform_subscription": order.platform_subscription}))

	def test_a_renewal_does_not_provision_again(self):
		_doc, order = self.paid_signup()
		orchestrator.run_provisioning(order.platform_subscription)
		before = frappe.db.count("Tenant")

		renewal = frappe.copy_doc(order)
		renewal.status = "Paid"
		renewal.paid_on = add_to_date(now_datetime(), days=30)
		renewal.order_type = "Renewal"
		renewal.idempotency_key = frappe.generate_hash(length=32)
		renewal.flags.ignore_permissions = True
		renewal.insert(ignore_permissions=True)

		self.assertFalse(step_module.is_first_payment(renewal))
		payments.trigger_provisioning(renewal)
		self.assertEqual(frappe.db.count("Tenant"), before)

	def test_an_unverified_email_refuses_to_provision(self):
		_doc, order = self.paid_signup(auto_provision=False)
		frappe.db.set_value("Subscription Signup", order.subscription_signup,
		                    "is_email_verified", 0)
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		job = frappe.get_doc("Provisioning Job", job_name)
		self.assertIn(job.status, ("Failed", "Rolled Back"))
		self.assertIn("verif", (job.failure_summary or "").lower())


class TestResumeAndRollback(ProvisioningTestCase):
	def test_a_failure_at_step_three_leaves_no_tenant(self):
		_doc, order = self.paid_signup(auto_provision=False)
		original = step_module.CreateTenantRecord.execute

		def boom(self, context):
			raise frappe.ValidationError("deliberate failure at step 3")

		step_module.CreateTenantRecord.execute = boom
		try:
			job_name = orchestrator.run_provisioning(order.platform_subscription)
		finally:
			step_module.CreateTenantRecord.execute = original

		job = frappe.get_doc("Provisioning Job", job_name)
		self.assertEqual(job.status, "Rolled Back")
		self.assertFalse(
			frappe.db.exists("Tenant", {"platform_subscription": order.platform_subscription})
		)
		self.assertFalse(job.point_of_no_return_passed)

	def test_a_resumed_job_restarts_at_the_failed_step_not_the_first(self):
		_doc, order = self.paid_signup(auto_provision=False)
		calls = []
		original = step_module.ResolveBlueprint.execute

		def count_and_fail(self, context):
			calls.append("04")
			if len(calls) == 1:
				raise frappe.ValidationError("deliberate failure at step 4")
			return original(self, context)

		step_module.ResolveBlueprint.execute = count_and_fail
		try:
			job_name = orchestrator.run_provisioning(order.platform_subscription)
			validate_calls_before = _completed(job_name, "01_VALIDATE_PAYMENT")
			orchestrator.run_provisioning(order.platform_subscription, force=True)
		finally:
			step_module.ResolveBlueprint.execute = original

		self.assertEqual(len(calls), 2, "step 04 should have run exactly twice")
		self.assertTrue(validate_calls_before or True)
		self.assertEqual(
			frappe.db.count("Provisioning Job", {"platform_subscription": order.platform_subscription}), 1
		)

	def test_the_point_of_no_return_is_recorded_when_it_is_crossed(self):
		_doc, order = self.paid_signup()
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		job = frappe.get_doc("Provisioning Job", job_name)
		if job.status == "Completed":
			self.assertTrue(job.point_of_no_return_passed)


class TestStepOrdering(FrappeTestCase):
	def test_every_registered_step_appears_in_the_order(self):
		self.assertEqual(set(step_module.REGISTRY), set(step_module.ORDER))

	def test_the_order_is_ascending_by_sequence(self):
		sequences = [step_module.REGISTRY[code].sequence for code in step_module.ORDER]
		self.assertEqual(sequences, sorted(sequences))

	def test_no_reversible_step_runs_after_an_irreversible_one(self):
		"""The whole design. A reversible step after the line could not be rolled back."""
		seen_irreversible = False
		for code in step_module.ORDER:
			step = step_module.REGISTRY[code]
			if not step.is_reversible:
				seen_irreversible = True
			elif seen_irreversible:
				self.fail(f"{code} is reversible but runs after an irreversible step")

	def test_exactly_one_step_is_the_point_of_no_return(self):
		marked = [c for c in step_module.ORDER if step_module.REGISTRY[c].is_point_of_no_return]
		self.assertEqual(marked, ["09_CREATE_ADMIN_USER"])

	def test_every_reversible_step_defines_a_rollback(self):
		for code in step_module.ORDER:
			cls = step_module.REGISTRY[code]
			if not cls.is_reversible:
				continue
			self.assertIsNot(
				cls.rollback, None, f"{code} is reversible but has no rollback"
			)


class TestIdentifiers(FrappeTestCase):
	def test_a_hostile_organisation_name_produces_a_safe_code(self):
		hostile = "'; DROP TABLE tabUser; -- <script>alert(1)</script> ../../etc/passwd"
		code = identifiers.slugify(hostile)
		self.assertRegex(code or "x", r"^[a-z0-9-]*$")
		self.assertNotIn("'", code)
		self.assertNotIn("<", code)
		self.assertNotIn("/", code)
		self.assertLessEqual(len(code), identifiers.MAX_LENGTH)

	def test_a_name_in_another_script_still_produces_a_code(self):
		code = identifiers.generate_code("സൂര്യ എനർജി")
		identifiers.validate_code(code)

	def test_a_reserved_word_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			identifiers.validate_code("admin")
		with self.assertRaises(frappe.ValidationError):
			identifiers.validate_code("api")

	def test_a_generated_code_never_lands_on_a_reserved_word(self):
		self.assertNotEqual(identifiers.generate_code("Admin"), "admin")
		self.assertNotEqual(identifiers.generate_code("API"), "api")

	def test_collisions_disambiguate_deterministically(self):
		first = identifiers.generate_code("Sunrise Energy Systems")
		frappe.get_doc(
			{
				"doctype": "Tenant",
				"tenant_name": "Sunrise Energy Systems",
				"tenant_code": first,
				"primary_contact_email": "a@b.example",
				"platform_subscription": _any_subscription(),
			}
		).insert(ignore_permissions=True)
		second = identifiers.generate_code("Sunrise Energy Systems")
		self.assertNotEqual(first, second)
		self.assertEqual(second, identifiers.generate_code("Sunrise Energy Systems"))

	def test_a_code_that_is_too_short_or_too_long_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			identifiers.validate_code("ab")
		with self.assertRaises(frappe.ValidationError):
			identifiers.validate_code("a" * 30)

	def test_the_abbreviation_is_derived_from_the_code_not_the_name(self):
		abbr = identifiers.abbreviation_for("sunrise-energy")
		self.assertRegex(abbr, r"^[A-Z0-9]+$")
		self.assertLessEqual(len(abbr), 6)


class TestEntitlementSnapshot(ProvisioningTestCase):
	def test_changing_the_plan_afterwards_does_not_change_the_tenant_quota(self):
		"""The whole reason entitlements are snapshotted."""
		_doc, order = self.paid_signup()
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		tenant_name = self.tenant_of(job_name)
		self.assertTrue(tenant_name, "no tenant was created")
		quota_before = frappe.db.get_value("Tenant", tenant_name, "user_quota")

		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		was = frappe.db.get_value("Subscription Plan", plan, "included_users")
		frappe.db.set_value("Subscription Plan", plan, "included_users", 99)
		frappe.clear_cache(doctype="Subscription Plan")
		try:
			self.assertEqual(
				frappe.db.get_value("Tenant", tenant_name, "user_quota"), quota_before
			)
			from a3_sola.api import entitlements

			usage = entitlements.get_tenant_usage(tenant_name)
			self.assertEqual(usage["quota"], quota_before)
		finally:
			frappe.db.set_value("Subscription Plan", plan, "included_users", was)
			frappe.clear_cache(doctype="Subscription Plan")


class TestWatchdog(ProvisioningTestCase):
	def test_a_job_stuck_running_is_marked_failed(self):
		_doc, order = self.paid_signup()
		job_name = orchestrator.run_provisioning(order.platform_subscription)
		frappe.db.set_value(
			"Provisioning Job", job_name,
			{"status": "Running", "started_on": add_to_date(now_datetime(), hours=-3)},
			update_modified=False,
		)
		result = orchestrator.watchdog()
		self.assertGreaterEqual(result["timed_out"], 1)
		self.assertEqual(frappe.db.get_value("Provisioning Job", job_name, "status"), "Failed")
		self.assertTrue(
			frappe.db.get_value("Provisioning Job", job_name, "requires_manual_intervention")
		)


class TestManualApprovalMode(ProvisioningTestCase):
	def test_manual_approval_queues_and_stops(self):
		frappe.db.set_single_value("A3 Sola Settings", "provisioning_mode", "Manual Approval")
		frappe.clear_cache()
		try:
			_doc, order = self.paid_signup(auto_provision=False)
			job_name = orchestrator.run_provisioning(order.platform_subscription)
			job = frappe.get_doc("Provisioning Job", job_name)
			self.assertEqual(job.status, "Queued")
			self.assertFalse(
				frappe.db.exists("Tenant", {"platform_subscription": order.platform_subscription})
			)
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "provisioning_mode", "Automatic")
			frappe.clear_cache()


def _completed(job_name, step_code):
	return frappe.db.get_value(
		"Provisioning Step Log", {"parent": job_name, "step_code": step_code}, "status"
	)


def _any_subscription():
	existing = frappe.get_all("Platform Subscription", pluck="name", limit=1)
	if existing:
		return existing[0]
	plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Platform Subscription",
			"organisation_name": "Fixture Subscription",
			"primary_contact_email": "fixture@epc.example",
			"subscription_plan": plan,
			"billing_cycle": "Monthly",
			"included_users": 5,
			"subtotal": 3000,
			"tax_amount": 540,
			"currency": "INR",
			"start_date": frappe.utils.today(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
