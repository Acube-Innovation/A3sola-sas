# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The public funnel, attacked the way it will actually be attacked.

These endpoints are unauthenticated and sit on the same instance as every tenant's
business data. The most important test in this file is the last one: that a guest cannot
read a Subscription Signup or a Demo Request through the ordinary API.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, flt, now_datetime, set_request

from a3_sola.api import ratelimit, signup

VALID = {
	"full_name": "Rajesh Kumar",
	"work_email": "rajesh@sunpowerepc.example",
	"phone": "9847012345",
	"designation": "Managing Partner",
	"organisation_name": "Sunpower EPC",
	"organisation_type": "Solar EPC",
	"city": "Ernakulam",
	"state": "Kerala",
	"country": "India",
	"approximate_monthly_installations": "10-50",
	"plan_code": "starter",
	"billing_cycle": "Monthly",
	"additional_users": 0,
	"accepted_terms": 1,
	"marketing_consent": 0,
	"utm_source": "google",
	"utm_medium": "cpc",
	"utm_campaign": "kerala-solar",
}


def payload(**overrides):
	data = dict(VALID)
	data.update(overrides)
	return data


def clear_limits():
	"""Rate limits persist in the cache across tests; each test starts from a clean slate."""
	ratelimit.reset_all()


class SignupTestCase(FrappeTestCase):
	def setUp(self):
		set_request(method="POST", path="/api/method/a3_sola.api.signup.submit_signup")
		clear_limits()
		frappe.db.delete("Subscription Signup", {"work_email": ["like", "%@%.example"]})
		frappe.db.delete("Demo Request", {"work_email": ["like", "%@%.example"]})

	def tearDown(self):
		frappe.set_user("Administrator")
		clear_limits()

	def _submit(self, **overrides):
		return signup.submit_signup(payload(**overrides))

	def _record(self, email=VALID["work_email"]):
		name = frappe.db.get_value("Subscription Signup", {"work_email": email}, "name")
		return frappe.get_doc("Subscription Signup", name) if name else None


class TestSignupCreation(SignupTestCase):
	def test_a_valid_signup_creates_a_record(self):
		result = self._submit()
		self.assertTrue(result["ok"])
		doc = self._record()
		self.assertTrue(doc)
		self.assertEqual(doc.status, "Awaiting Email Verification")
		self.assertEqual(doc.plan_code, "starter")

	def test_the_price_is_snapshotted_at_signup(self):
		self._submit()
		doc = self._record()
		self.assertEqual(flt(doc.base_amount, 2), 3000.00)
		self.assertEqual(flt(doc.implementation_fee, 2), 10000.00)
		self.assertEqual(flt(doc.total_amount, 2), 13000.00)
		self.assertTrue(frappe.parse_json(doc.price_breakdown))

	def test_the_snapshot_does_not_move_when_the_plan_price_changes(self):
		"""The whole reason the snapshot exists. Charge what they agreed to."""
		self._submit()
		doc = self._record()
		original_total = flt(doc.total_amount, 2)

		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		was = frappe.db.get_value("Subscription Plan", plan, "monthly_price")
		frappe.db.set_value("Subscription Plan", plan, "monthly_price", 9999)
		frappe.clear_cache(doctype="Subscription Plan")
		try:
			doc.reload()
			self.assertEqual(flt(doc.total_amount, 2), original_total)
			self.assertEqual(flt(doc.base_amount, 2), 3000.00)
		finally:
			frappe.db.set_value("Subscription Plan", plan, "monthly_price", was)
			frappe.clear_cache(doctype="Subscription Plan")

	def test_annual_signup_snapshots_the_waived_implementation_fee(self):
		self._submit(billing_cycle="Annual")
		doc = self._record()
		self.assertEqual(flt(doc.implementation_fee, 2), 0.00)
		self.assertEqual(flt(doc.total_amount, 2), 30000.00)

	def test_additional_users_are_priced_and_counted(self):
		self._submit(additional_users=3)
		doc = self._record()
		self.assertEqual(doc.additional_users, 3)
		self.assertEqual(doc.total_users, 8)
		self.assertEqual(flt(doc.additional_user_amount, 2), 900.00)

	def test_attribution_is_captured(self):
		self._submit()
		doc = self._record()
		self.assertEqual(doc.utm_source, "google")
		self.assertEqual(doc.utm_campaign, "kerala-solar")

	def test_creation_is_logged(self):
		self._submit()
		doc = self._record()
		events = [row.event_type for row in doc.event_log]
		self.assertIn("Created", events)
		self.assertIn("Email Sent", events)

	def test_the_response_never_returns_the_record(self):
		result = self._submit()
		self.assertEqual(set(result.keys()), {"ok", "message", "reference", "next"})
		self.assertNotIn("verification_token", frappe.as_json(result))
		self.assertNotIn("ip_address", frappe.as_json(result))


class TestDuplicateAndNeutrality(SignupTestCase):
	def test_a_duplicate_email_resends_rather_than_duplicating(self):
		first = self._submit()
		second = self._submit()
		self.assertEqual(
			frappe.db.count("Subscription Signup", {"work_email": VALID["work_email"]}), 1
		)
		self.assertEqual(second["reference"], first["reference"])

	def test_the_response_body_is_identical_either_way(self):
		"""A different message on the second attempt would confirm the email exists."""
		first = self._submit()
		second = self._submit()
		self.assertEqual(first["message"], second["message"])
		self.assertEqual(first["ok"], second["ok"])

	def test_a_resend_on_an_unknown_reference_looks_the_same_as_a_known_one(self):
		self._submit()
		doc = self._record()
		known = signup.resend_verification(doc.name)
		clear_limits()
		unknown = signup.resend_verification("SGN-2026-99999")
		self.assertEqual(known["message"], unknown["message"])
		self.assertEqual(known["ok"], unknown["ok"])


class TestAbuseControls(SignupTestCase):
	def test_a_honeypot_submission_creates_nothing(self):
		before = frappe.db.count("Subscription Signup")
		result = self._submit(website_url="http://spam.example")
		self.assertTrue(result["ok"], "the bot must not learn it was caught")
		self.assertIsNone(result["reference"])
		self.assertEqual(frappe.db.count("Subscription Signup"), before)

	def test_the_sixth_attempt_from_one_ip_is_throttled(self):
		for index in range(5):
			self._submit(work_email=f"person{index}@epc{index}.example")
		with self.assertRaises(frappe.TooManyRequestsError):
			self._submit(work_email="person6@epc6.example")

	def test_the_throttle_message_never_states_the_limit(self):
		for index in range(5):
			self._submit(work_email=f"burst{index}@epc{index}.example")
		try:
			self._submit(work_email="burst6@epc6.example")
			self.fail("expected a throttle")
		except frappe.TooManyRequestsError as exc:
			message = str(exc)
			self.assertNotIn("5", message)
			self.assertNotIn("limit", message.lower())

	def test_the_same_email_is_capped_per_day(self):
		"""One email cannot be reused all day, even from a fresh IP each time.

		Only the per-IP counter is cleared between attempts here - clearing everything
		would reset the very limit under test.
		"""
		for _index in range(3):
			ratelimit.reset("signup_ip", ratelimit.client_ip())
			signup.submit_signup(payload(work_email="repeat@epc.example"))
			frappe.db.delete("Subscription Signup", {"work_email": "repeat@epc.example"})

		ratelimit.reset("signup_ip", ratelimit.client_ip())
		with self.assertRaises(frappe.TooManyRequestsError):
			signup.submit_signup(payload(work_email="repeat@epc.example"))

	def test_a_demo_request_honeypot_creates_nothing(self):
		before = frappe.db.count("Demo Request")
		result = signup.submit_demo_request(
			{
				"full_name": "Bot",
				"work_email": "bot@spam.example",
				"phone": "9847012345",
				"organisation_name": "Spam",
				"website_url": "http://spam.example",
			}
		)
		self.assertTrue(result["ok"])
		self.assertEqual(frappe.db.count("Demo Request"), before)


class TestValidation(SignupTestCase):
	def test_a_malformed_email_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(work_email="not-an-email")

	def test_a_blocked_domain_is_refused(self):
		frappe.db.set_single_value(
			"A3 Sola Settings", "disposable_email_domains", "mailinator.com\nspam.example"
		)
		frappe.clear_cache()
		try:
			with self.assertRaises(frappe.ValidationError):
				self._submit(work_email="throwaway@mailinator.com")
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "disposable_email_domains", "")
			frappe.clear_cache()

	def test_a_subdomain_of_a_blocked_domain_is_refused(self):
		frappe.db.set_single_value("A3 Sola Settings", "disposable_email_domains", "mailinator.com")
		frappe.clear_cache()
		try:
			with self.assertRaises(frappe.ValidationError):
				self._submit(work_email="throwaway@mail.mailinator.com")
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "disposable_email_domains", "")
			frappe.clear_cache()

	def test_the_email_is_normalised_to_lowercase(self):
		self._submit(work_email="Rajesh@SunpowerEPC.Example")
		self.assertTrue(self._record("rajesh@sunpowerepc.example"))

	def test_a_non_indian_mobile_is_refused_for_india(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(phone="12345")

	def test_a_bad_gstin_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(gstin="NOT-A-GSTIN")

	def test_a_valid_gstin_is_accepted_and_uppercased(self):
		self._submit(gstin="32aabcs1429b1zx")
		self.assertEqual(self._record().gstin, "32AABCS1429B1ZX")

	def test_a_missing_name_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(full_name="")

	def test_additional_users_beyond_the_plan_limit_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(additional_users=500)

	def test_a_custom_plan_cannot_be_bought_self_serve(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(plan_code="enterprise")

	def test_an_unknown_plan_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._submit(plan_code="free-forever")

	def test_signup_can_be_switched_off(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_public_signup", 0)
		frappe.clear_cache()
		try:
			with self.assertRaises(frappe.ValidationError):
				self._submit()
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "enable_public_signup", 1)
			frappe.clear_cache()


class TestVerification(SignupTestCase):
	def _token(self):
		self._submit()
		doc = self._record()
		return doc, doc.verification_token

	def test_a_valid_token_verifies(self):
		doc, token = self._token()
		result = signup.verify_email(token)
		self.assertTrue(result["ok"])
		doc.reload()
		self.assertTrue(doc.is_email_verified)
		self.assertEqual(doc.status, "Verified")

	def test_the_token_is_burned_after_use(self):
		doc, token = self._token()
		signup.verify_email(token)
		doc.reload()
		self.assertFalse(doc.verification_token)

	def test_a_reused_token_is_refused(self):
		_doc, token = self._token()
		signup.verify_email(token)
		with self.assertRaises(frappe.ValidationError):
			signup.verify_email(token)

	def test_an_expired_token_is_refused(self):
		doc, token = self._token()
		frappe.db.set_value(
			"Subscription Signup", doc.name, "token_expires_on",
			add_to_date(now_datetime(), hours=-1), update_modified=False,
		)
		with self.assertRaises(frappe.ValidationError):
			signup.verify_email(token)

	def test_a_wrong_token_is_refused(self):
		self._token()
		with self.assertRaises(frappe.ValidationError):
			signup.verify_email("clearly-not-a-real-token")

	def test_every_failure_reads_the_same(self):
		"""Expired, reused, wrong and never-existed must be indistinguishable."""
		doc, token = self._token()
		signup.verify_email(token)

		messages = set()
		for bad in (token, "never-existed", ""):
			try:
				signup.verify_email(bad)
			except Exception as exc:
				messages.add(str(exc))
		self.assertEqual(len(messages), 1, f"failures are distinguishable: {messages}")

	def test_attempts_are_capped(self):
		doc, _token = self._token()
		frappe.db.set_value(
			"Subscription Signup", doc.name, "verification_attempts", 50, update_modified=False
		)
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			signup.verify_email(doc.verification_token)

	def test_verification_is_logged(self):
		doc, token = self._token()
		signup.verify_email(token)
		doc.reload()
		self.assertIn("Email Verified", [row.event_type for row in doc.event_log])


class TestPlanChange(SignupTestCase):
	def _verified(self):
		self._submit()
		doc = self._record()
		signup.verify_email(doc.verification_token)
		doc.reload()
		return doc, signup._summary_key(doc)

	def test_a_verified_applicant_can_change_plan(self):
		doc, key = self._verified()
		result = signup.update_plan_selection(doc.name, key, "growth", "Annual", 2)
		self.assertEqual(result["plan_code"], "growth")
		self.assertEqual(result["billing_cycle"], "Annual")
		self.assertEqual(result["additional_users"], 2)

	def test_the_price_is_re_snapshotted_on_change(self):
		doc, key = self._verified()
		signup.update_plan_selection(doc.name, key, "growth", "Annual", 0)
		doc.reload()
		self.assertEqual(flt(doc.base_amount, 2), 60000.00)
		self.assertEqual(flt(doc.implementation_fee, 2), 0.00)

	def test_a_plan_change_is_logged(self):
		doc, key = self._verified()
		signup.update_plan_selection(doc.name, key, "growth", "Monthly", 0)
		doc.reload()
		self.assertIn("Plan Changed", [row.event_type for row in doc.event_log])

	def test_the_reference_alone_is_not_enough(self):
		"""A reference appears in a URL. Guessing one must not re-price somebody's signup."""
		doc, _key = self._verified()
		with self.assertRaises(frappe.DoesNotExistError):
			signup.update_plan_selection(doc.name, "guessed-key", "growth", "Annual", 0)

	def test_a_custom_plan_cannot_be_switched_to(self):
		doc, key = self._verified()
		with self.assertRaises(frappe.ValidationError):
			signup.update_plan_selection(doc.name, key, "enterprise", "Monthly", 0)


class TestSummary(SignupTestCase):
	def _verified(self):
		self._submit()
		doc = self._record()
		signup.verify_email(doc.verification_token)
		doc.reload()
		return doc, signup._summary_key(doc)

	def test_the_summary_returns_what_the_page_needs(self):
		doc, key = self._verified()
		summary = signup.get_signup_summary(doc.name, key)
		self.assertEqual(summary["organisation_name"], "Sunpower EPC")
		self.assertEqual(summary["plan_name"], "Starter")
		self.assertTrue(summary["line_items"])

	def test_the_summary_never_leaks_an_internal_field(self):
		doc, key = self._verified()
		summary = signup.get_signup_summary(doc.name, key)
		for forbidden in (
			"verification_token", "ip_address", "user_agent", "token_expires_on",
			"price_breakdown", "event_log",
		):
			self.assertNotIn(forbidden, summary, f"{forbidden} leaked to the summary page")

	def test_the_summary_needs_the_key(self):
		doc, _key = self._verified()
		with self.assertRaises(frappe.DoesNotExistError):
			signup.get_signup_summary(doc.name, "not-the-key")

	def test_a_guessed_reference_looks_the_same_as_a_wrong_key(self):
		doc, _key = self._verified()
		messages = set()
		for reference, key in ((doc.name, "wrong"), ("SGN-2026-99999", "wrong")):
			try:
				signup.get_signup_summary(reference, key)
			except Exception as exc:
				messages.add(str(exc))
		self.assertEqual(len(messages), 1)


class TestPhaseFiveContract(SignupTestCase):
	def test_initiate_payment_is_declared_but_not_implemented(self):
		with self.assertRaises(NotImplementedError):
			signup.initiate_payment("SGN-0001", "key")

	def test_its_docstring_states_the_contract(self):
		doc = signup.initiate_payment.__doc__ or ""
		self.assertIn("snapshot", doc.lower())
		self.assertIn("Awaiting Payment", doc)

	def test_the_funnel_still_completes_without_payments(self):
		self._submit()
		doc = self._record()
		signup.verify_email(doc.verification_token)
		doc.reload()
		result = signup.request_payment_contact(doc.name, signup._summary_key(doc))
		self.assertTrue(result["ok"])
		self.assertTrue(result["pending"])


class TestNothingPrivilegedIsCreated(SignupTestCase):
	def test_no_user_company_or_role_is_created_by_a_signup(self):
		"""Phase 6 provisions, after payment. Not here, and not from public input."""
		before = {
			dt: frappe.db.count(dt) for dt in ("User", "Company", "Customer", "Role", "Contact")
		}
		self._submit()
		doc = self._record()
		signup.verify_email(doc.verification_token)
		after = {
			dt: frappe.db.count(dt) for dt in ("User", "Company", "Customer", "Role", "Contact")
		}
		self.assertEqual(before, after, "the public funnel created a privileged record")

	def test_the_module_never_calls_a_privileged_creation(self):
		import inspect

		source = inspect.getsource(signup)
		for forbidden in (
			'"doctype": "User"', '"doctype": "Company"', '"doctype": "Role"',
			'"doctype": "Customer"', "add_roles(", "frappe.db.set_value(",
		):
			self.assertNotIn(
				forbidden, source, f"signup.py contains a privileged operation: {forbidden}"
			)


class TestGuestCannotReadTheFunnel(FrappeTestCase):
	"""The most important test in this file.

	These records hold names, emails, phone numbers and what somebody agreed to pay. If a
	guest can read them through the ordinary API, everything else here is decoration.
	"""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_cannot_list_signups(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Subscription Signup", ignore_permissions=False)

	def test_guest_cannot_list_demo_requests(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Demo Request", ignore_permissions=False)

	def test_guest_cannot_read_a_signup_by_name(self):
		frappe.set_user("Administrator")
		set_request(method="POST", path="/api/method/x")
		clear_limits()
		frappe.db.delete("Subscription Signup", {"work_email": "guestprobe@epc.example"})
		signup.submit_signup(payload(work_email="guestprobe@epc.example"))
		name = frappe.db.get_value(
			"Subscription Signup", {"work_email": "guestprobe@epc.example"}, "name"
		)

		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Subscription Signup", name).check_permission("read")

	def test_guest_has_no_write_anywhere_in_the_funnel(self):
		for doctype in ("Subscription Signup", "Demo Request", "Signup Event Log"):
			for row in frappe.get_meta(doctype).permissions:
				if row.role != "Guest":
					continue
				for ptype in ("read", "write", "create", "delete", "report", "export"):
					self.assertFalse(
						row.get(ptype), f"Guest has {ptype} on {doctype}"
					)


class TestEveryGuestEndpointIsLimited(FrappeTestCase):
	"""An unauthenticated endpoint with no limit is an unauthenticated endpoint that can be
	hammered. The two key-guarded reads count: guessing the key is the attack on them."""

	def test_every_allow_guest_endpoint_in_the_funnel_is_rate_limited(self):
		import inspect

		unlimited = []
		source = inspect.getsource(signup)
		blocks = source.split("@frappe.whitelist(allow_guest=True)")
		for block in blocks[1:]:
			head = block.split("def ", 1)
			name = head[1].split("(")[0] if len(head) > 1 else "?"
			decorators = head[0]
			if "rate_limited" not in decorators:
				unlimited.append(name)
		self.assertEqual(
			unlimited, [], f"these public endpoints have no rate limit: {unlimited}"
		)

	def test_the_pricing_endpoint_is_pure_so_needs_no_limit(self):
		"""The one unlimited public endpoint, and the reason it is allowed to be."""
		import inspect

		from a3_sola.api import platform

		body = inspect.getsource(platform.calculate_plan_total)
		for forbidden in ("insert(", ".save(", "db.set_value", "db.sql"):
			self.assertNotIn(forbidden, body, "calculate_plan_total writes; it must be limited")
