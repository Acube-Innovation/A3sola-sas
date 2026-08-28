# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Payments foundation.

The most important assertions here are the boring ones: that the amount charged is the
amount the customer agreed to, that a double-click cannot charge twice, and that the paise
conversion produces the exact integer rather than one a floating-point round-trip left a
paisa short.

NO TEST IN THIS FILE MAY REACH THE LIVE RAZORPAY API. `get_client()` returns the mock
whenever `frappe.flags.in_test` is set, and there is a test below asserting exactly that.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, set_request

from a3_sola.api import payments, ratelimit, signup, tax
from a3_sola.api.gateways import razorpay_client
from a3_sola.tests.platform.test_signup import payload


def clear_limits():
	ratelimit.reset_all()


class PaymentTestCase(FrappeTestCase):
	def setUp(self):
		set_request(method="POST", path="/api/method/a3_sola.api.payments.initiate_payment")
		clear_limits()
		frappe.flags.mock_gateway_behaviour = "success"
		frappe.db.set_single_value("A3 Sola Settings", "company_state_code", "32")
		frappe.db.set_single_value("A3 Sola Settings", "subscription_gst_rate", 18)
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.clear_cache()
		frappe.db.delete("Subscription Signup", {"work_email": ["like", "%@%.example"]})

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.set_user("Administrator")
		clear_limits()

	def _verified_signup(self, **overrides):
		signup.submit_signup(payload(**overrides))
		name = frappe.db.get_value(
			"Subscription Signup",
			{"work_email": overrides.get("work_email", "rajesh@sunpowerepc.example")},
			"name",
		)
		doc = frappe.get_doc("Subscription Signup", name)
		signup.verify_email(doc.verification_token)
		doc.reload()
		return doc, signup._summary_key(doc)


class TestSnapshotIsWhatIsCharged(PaymentTestCase):
	def test_the_order_copies_the_signup_snapshot(self):
		doc, _key = self._verified_signup()
		order = payments.build_order_from_signup(doc)
		self.assertEqual(flt(order.base_amount, 2), flt(doc.base_amount, 2))
		self.assertEqual(flt(order.implementation_fee, 2), flt(doc.implementation_fee, 2))
		self.assertEqual(flt(order.subtotal, 2), flt(doc.subtotal, 2))

	def test_editing_the_plan_price_afterwards_does_not_change_the_charge(self):
		"""The whole reason the snapshot exists."""
		doc, key = self._verified_signup()
		charged_before = flt(doc.subtotal, 2)

		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		was = frappe.db.get_value("Subscription Plan", plan, "monthly_price")
		frappe.db.set_value("Subscription Plan", plan, "monthly_price", 99999)
		frappe.clear_cache(doctype="Subscription Plan")
		try:
			result = payments.initiate_payment(doc.name, key)
			order = frappe.get_doc("Payment Order", result["payment_order"])
			self.assertEqual(flt(order.subtotal, 2), charged_before)
			self.assertNotEqual(flt(order.subtotal, 2), 99999.00)
		finally:
			frappe.db.set_value("Subscription Plan", plan, "monthly_price", was)
			frappe.clear_cache(doctype="Subscription Plan")

	def test_the_payments_module_never_recomputes_a_price(self):
		"""Parsed, not grepped - the module docstring mentions the function by name
		precisely to say it is not called."""
		import ast
		import inspect

		tree = ast.parse(inspect.getsource(payments))
		called = set()
		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			target = node.func
			name = getattr(target, "attr", None) or getattr(target, "id", None)
			if name:
				called.add(name)
		self.assertNotIn(
			"calculate_plan_total", called,
			"payments.py recomputes the price instead of charging the snapshot",
		)


class TestIdempotency(PaymentTestCase):
	def test_a_double_click_creates_one_order(self):
		doc, key = self._verified_signup()
		first = payments.initiate_payment(doc.name, key)
		second = payments.initiate_payment(doc.name, key)
		self.assertEqual(first["payment_order"], second["payment_order"])
		self.assertEqual(
			frappe.db.count("Payment Order", {"subscription_signup": doc.name}), 1
		)

	def test_the_key_is_deterministic_for_the_same_period(self):
		first = payments.idempotency_key("Subscription Signup", "SGN-1", "Renewal", "2026-09-01")
		second = payments.idempotency_key("Subscription Signup", "SGN-1", "Renewal", "2026-09-01")
		self.assertEqual(first, second)

	def test_a_different_period_gets_a_different_key(self):
		september = payments.idempotency_key("Subscription Signup", "SGN-1", "Renewal", "2026-09-01")
		october = payments.idempotency_key("Subscription Signup", "SGN-1", "Renewal", "2026-10-01")
		self.assertNotEqual(september, october)

	def test_the_gateway_order_is_created_once(self):
		doc, key = self._verified_signup()
		first = payments.initiate_payment(doc.name, key)
		order_id = first["order_id"]
		second = payments.initiate_payment(doc.name, key)
		self.assertEqual(second["order_id"], order_id)


class TestPaiseConversion(FrappeTestCase):
	def test_common_amounts_convert_to_exact_integers(self):
		"""int(3540.00 * 100) can be 353999. This is the customer's actual charge."""
		for rupees, paise in (
			(3540.00, 354000), (7080.00, 708000), (35400.00, 3540000),
			(70800.00, 7080000), (3540.50, 354050), (0.01, 1), (15000.00, 1500000),
			(15001.00, 1500100), (1062.00, 106200), (13924.80, 1392480),
		):
			self.assertEqual(
				tax.to_paise(rupees), paise, f"{rupees} converted wrong"
			)
			self.assertIsInstance(tax.to_paise(rupees), int)

	def test_the_round_trip_is_lossless(self):
		for rupees in (3540.00, 70800.00, 13924.80, 0.05):
			self.assertEqual(flt(tax.from_paise(tax.to_paise(rupees)), 2), flt(rupees, 2))


class TestSubscriptionTax(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value("A3 Sola Settings", "company_state_code", "32")
		frappe.db.set_single_value("A3 Sola Settings", "subscription_gst_rate", 18)
		frappe.clear_cache()

	def test_a_kerala_customer_gets_cgst_and_sgst(self):
		split = tax.compute_tax(3000, "32")
		self.assertEqual(split["tax_type"], "CGST+SGST")
		self.assertEqual(flt(split["cgst_amount"], 2), 270.00)
		self.assertEqual(flt(split["sgst_amount"], 2), 270.00)
		self.assertEqual(flt(split["igst_amount"], 2), 0.00)

	def test_a_karnataka_customer_gets_igst(self):
		split = tax.compute_tax(3000, "29")
		self.assertEqual(split["tax_type"], "IGST")
		self.assertEqual(flt(split["igst_amount"], 2), 540.00)
		self.assertEqual(flt(split["cgst_amount"], 2), 0.00)

	def test_the_components_always_add_back_to_the_total(self):
		for taxable in (3000, 6000, 30000, 60000, 1234.56, 999.99):
			split = tax.compute_tax(taxable, "32")
			summed = flt(
				split["igst_amount"] + split["cgst_amount"] + split["sgst_amount"], 2
			)
			self.assertEqual(summed, flt(split["total_tax"], 2), f"{taxable} does not add up")

	def test_the_rate_comes_from_settings_not_from_code(self):
		import inspect

		source = inspect.getsource(tax.compute_tax)
		self.assertIn("subscription_gst_rate", source)
		self.assertNotIn("0.18", source)
		self.assertNotIn("* 18", source)

	def test_a_gstin_whose_state_contradicts_the_address_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			# A Kerala GSTIN with a Karnataka state code.
			tax.validate_gstin("32AABCS1429B1ZX", "29")

	def test_a_matching_gstin_is_accepted(self):
		self.assertEqual(tax.validate_gstin("32aabcs1429b1zx", "32"), "32AABCS1429B1ZX")

	def test_a_malformed_gstin_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			tax.validate_gstin("NOTAGSTIN", "32")

	def test_the_gstin_decides_the_place_of_supply(self):
		code, _place = tax.resolve_place_of_supply(
			customer_state="Karnataka", customer_gstin="32AABCS1429B1ZX"
		)
		self.assertEqual(code, "32", "the registered GSTIN should win over a typed address")


class TestCollectionClassification(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.clear_cache()

	def test_a_monthly_debit_under_the_ceiling_can_auto_debit(self):
		mode, reason = payments.classify_collection(7080.00, "Monthly")
		self.assertEqual(mode, "Auto Debit")
		self.assertIn("within the RBI ceiling", reason)

	def test_a_monthly_debit_over_the_ceiling_needs_authentication(self):
		mode, reason = payments.classify_collection(70800.00, "Monthly")
		self.assertEqual(mode, "Payment Link")
		self.assertIn("above the RBI", reason)

	def test_the_boundary_is_exact(self):
		self.assertEqual(payments.classify_collection(15000.00, "Monthly")[0], "Auto Debit")
		self.assertEqual(payments.classify_collection(15001.00, "Monthly")[0], "Payment Link")

	def test_annual_always_needs_authentication(self):
		"""Even a tiny annual amount: a mandate asked to fire a year later fails too often."""
		for amount in (1000.00, 35400.00, 70800.00):
			mode, reason = payments.classify_collection(amount, "Annual")
			self.assertEqual(mode, "Payment Link", f"{amount} annual should not auto-debit")
			self.assertIn("Annual billing", reason)

	def test_the_ceiling_is_a_setting_not_a_constant(self):
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 5000)
		frappe.clear_cache()
		try:
			self.assertEqual(payments.classify_collection(7080.00, "Monthly")[0], "Payment Link")
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
			frappe.clear_cache()

	def test_the_reason_is_written_for_a_customer_to_read(self):
		_mode, reason = payments.classify_collection(70800.00, "Annual")
		self.assertNotIn("afa_free_debit_ceiling", reason)
		self.assertGreater(len(reason), 60, "the reason should explain, not just label")


class TestSignatureVerification(FrappeTestCase):
	def test_a_valid_signature_verifies(self):
		import hashlib
		import hmac

		secret = "test_secret"
		expected = hmac.new(
			secret.encode(), b"order_1|pay_1", hashlib.sha256
		).hexdigest()
		self.assertTrue(
			razorpay_client.verify_payment_signature("order_1", "pay_1", expected, secret)
		)

	def test_a_tampered_signature_is_rejected(self):
		self.assertFalse(
			razorpay_client.verify_payment_signature("order_1", "pay_1", "deadbeef", "s")
		)

	def test_a_missing_signature_is_rejected(self):
		self.assertFalse(razorpay_client.verify_payment_signature("order_1", "pay_1", "", "s"))

	def test_a_webhook_signature_verifies_against_the_exact_bytes(self):
		import hashlib
		import hmac

		body = b'{"event":"payment.captured","x":1}'
		secret = "hook_secret"
		expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
		self.assertTrue(razorpay_client.verify_webhook_signature(body, expected, secret))
		# One byte different in the body and it must not verify.
		self.assertFalse(
			razorpay_client.verify_webhook_signature(b'{"event":"payment.captured","x":2}',
			                                         expected, secret)
		)

	def test_comparison_is_constant_time(self):
		import inspect

		source = inspect.getsource(razorpay_client)
		self.assertIn("hmac.compare_digest", source)
		self.assertNotIn("== signature", source)


class TestRedaction(FrappeTestCase):
	def test_a_card_number_never_survives_redaction(self):
		payload = {
			"id": "pay_1",
			"card": {"number": "4111111111111111", "last4": "1111", "network": "Visa"},
		}
		cleaned = razorpay_client.redact(payload)
		self.assertNotIn("number", cleaned["card"])
		self.assertEqual(cleaned["card"]["last4"], "1111")
		self.assertNotIn("4111111111111111", frappe.as_json(cleaned))

	def test_contact_details_are_stripped(self):
		cleaned = razorpay_client.redact(
			{"email": "a@b.example", "contact": "+919847012345", "vpa": "x@upi"}
		)
		for key in ("email", "contact", "vpa"):
			self.assertEqual(cleaned[key], razorpay_client.REDACTED)

	def test_tokens_and_secrets_are_stripped(self):
		cleaned = razorpay_client.redact(
			{"token": "tok_1", "key_secret": "sshh", "signature": "abc"}
		)
		for key in ("token", "key_secret", "signature"):
			self.assertEqual(cleaned[key], razorpay_client.REDACTED)

	def test_redaction_reaches_into_nested_structures(self):
		cleaned = razorpay_client.redact(
			{"payload": {"payment": {"entity": {"email": "a@b.example"}}}}
		)
		self.assertEqual(
			cleaned["payload"]["payment"]["entity"]["email"], razorpay_client.REDACTED
		)

	def test_a_stored_transaction_is_redacted_on_the_way_in(self):
		doc = frappe.get_doc(
			{
				"doctype": "Payment Transaction",
				"payment_order": None,
				"status": "Captured",
				"raw_response": frappe.as_json(
					{"card": {"number": "4111111111111111", "last4": "1111"},
					 "email": "a@b.example"}
				),
			}
		)
		doc.validate()
		self.assertNotIn("4111111111111111", doc.raw_response)
		self.assertNotIn("a@b.example", doc.raw_response)


class TestNoTestTouchesTheRealGateway(FrappeTestCase):
	def test_get_client_returns_the_mock_under_test(self):
		client = razorpay_client.get_client()
		self.assertIsInstance(client, razorpay_client.MockRazorpayClient)

	def test_the_mock_needs_no_credentials(self):
		"""A test site has none, and the mock must still work."""
		client = razorpay_client.MockRazorpayClient()
		order = client.create_order(354000, "INR", "PORD-1")
		self.assertTrue(order["id"].startswith("order_"))

	def test_the_mock_refuses_a_non_integer_amount(self):
		from a3_sola.api.gateways.exceptions import GatewayValidationError

		with self.assertRaises(GatewayValidationError):
			razorpay_client.MockRazorpayClient().create_order(3540.00, "INR", "PORD-1")


class TestInitiatePaymentGuards(PaymentTestCase):
	def test_the_token_is_required(self):
		doc, _key = self._verified_signup()
		with self.assertRaises(frappe.DoesNotExistError):
			payments.initiate_payment(doc.name, "not-the-key")

	def test_a_guessed_reference_alone_is_not_enough(self):
		with self.assertRaises(frappe.DoesNotExistError):
			payments.initiate_payment("SGN-2026-99999", "anything")

	def test_an_unverified_signup_cannot_pay(self):
		signup.submit_signup(payload(work_email="unverified@epc.example"))
		name = frappe.db.get_value(
			"Subscription Signup", {"work_email": "unverified@epc.example"}, "name"
		)
		doc = frappe.get_doc("Subscription Signup", name)
		with self.assertRaises(frappe.ValidationError):
			payments.initiate_payment(doc.name, signup._summary_key(doc))

	def test_the_response_carries_no_secret(self):
		doc, key = self._verified_signup()
		result = payments.initiate_payment(doc.name, key)
		body = frappe.as_json(result)
		self.assertNotIn("key_secret", body)
		self.assertNotIn("verification_token", body)
		for forbidden in ("razorpay_key_secret", "webhook_secret"):
			self.assertNotIn(forbidden, body)

	def test_the_response_carries_only_what_checkout_needs(self):
		doc, key = self._verified_signup()
		result = payments.initiate_payment(doc.name, key)
		self.assertEqual(
			set(result.keys()),
			{
				"order_id", "payment_order", "key_id", "amount", "currency", "name",
				"description", "prefill", "notes", "callback_url",
				"collection_mode_for_renewals", "renewal_note",
			},
		)

	def test_the_signup_moves_to_awaiting_payment(self):
		doc, key = self._verified_signup()
		payments.initiate_payment(doc.name, key)
		doc.reload()
		self.assertEqual(doc.status, "Awaiting Payment")
		self.assertIn("Payment Initiated", [row.event_type for row in doc.event_log])

	def test_a_gateway_outage_does_not_leave_a_half_state(self):
		doc, key = self._verified_signup()
		frappe.flags.mock_gateway_behaviour = "network-error"
		with self.assertRaises(frappe.ValidationError):
			payments.initiate_payment(doc.name, key)
		order = frappe.db.get_value(
			"Payment Order", {"subscription_signup": doc.name},
			["status", "gateway_order_id"], as_dict=True,
		)
		self.assertEqual(order.status, "Created")
		self.assertFalse(order.gateway_order_id, "no gateway id should be recorded")


class TestCheckoutVerification(PaymentTestCase):
	def _paid_setup(self, payment_id="pay_mock_1", **overrides):
		"""One gateway payment id per test.

		`PaymentTransaction.record` deduplicates by gateway payment id - correctly, since
		one payment must produce one row - so tests sharing an id would silently reuse
		each other's transactions.
		"""
		doc, key = self._verified_signup(**overrides)
		result = payments.initiate_payment(doc.name, key)
		order = frappe.get_doc("Payment Order", result["payment_order"])
		import hashlib
		import hmac

		secret = razorpay_client._secret("razorpay_key_secret") or ""
		signature = hmac.new(
			secret.encode(),
			f"{order.gateway_order_id}|{payment_id}".encode(),
			hashlib.sha256,
		).hexdigest()
		return doc, key, order, signature

	def test_a_valid_callback_marks_everything_paid(self):
		doc, key, order, signature = self._paid_setup("pay_valid_1")
		payments.verify_checkout_payment(
			{
				"signup_reference": doc.name,
				"token": key,
				"razorpay_order_id": order.gateway_order_id,
				"razorpay_payment_id": "pay_valid_1",
				"razorpay_signature": signature,
			}
		)
		order.reload()
		doc.reload()
		self.assertEqual(order.status, "Paid")
		self.assertEqual(doc.status, "Paid")

	def test_a_replayed_callback_changes_nothing(self):
		doc, key, order, signature = self._paid_setup("pay_replay_1")
		body = {
			"signup_reference": doc.name, "token": key,
			"razorpay_order_id": order.gateway_order_id,
			"razorpay_payment_id": "pay_replay_1", "razorpay_signature": signature,
		}
		payments.verify_checkout_payment(body)
		transactions = frappe.db.count("Payment Transaction", {"payment_order": order.name})
		payments.verify_checkout_payment(body)
		payments.verify_checkout_payment(body)
		self.assertEqual(
			frappe.db.count("Payment Transaction", {"payment_order": order.name}),
			transactions,
			"a replayed callback created another transaction",
		)
		order.reload()
		self.assertEqual(order.status, "Paid")

	def test_a_tampered_signature_is_refused_and_recorded(self):
		doc, key, order, _signature = self._paid_setup("pay_tampered_1")
		with self.assertRaises(frappe.ValidationError):
			payments.verify_checkout_payment(
				{
					"signup_reference": doc.name, "token": key,
					"razorpay_order_id": order.gateway_order_id,
					"razorpay_payment_id": "pay_tampered_1",
					"razorpay_signature": "deadbeef",
				}
			)
		order.reload()
		self.assertNotEqual(order.status, "Paid")
		self.assertTrue(
			frappe.db.exists("Payment Transaction",
			                 {"payment_order": order.name, "status": "Failed"})
		)

	def test_a_callback_for_another_signups_order_is_refused(self):
		doc, key, order, signature = self._paid_setup("pay_crosscheck_1")
		other, other_key = self._verified_signup(work_email="other@epc.example")
		with self.assertRaises(frappe.DoesNotExistError):
			payments.verify_checkout_payment(
				{
					"signup_reference": other.name, "token": other_key,
					"razorpay_order_id": order.gateway_order_id,
					"razorpay_payment_id": "pay_crosscheck_1",
					"razorpay_signature": signature,
				}
			)


class TestPaymentStatus(PaymentTestCase):
	def test_status_needs_the_key(self):
		doc, _key = self._verified_signup()
		with self.assertRaises(frappe.DoesNotExistError):
			payments.get_payment_status(doc.name, "wrong")

	def test_status_returns_only_what_the_page_needs(self):
		doc, key = self._verified_signup()
		payments.initiate_payment(doc.name, key)
		status = payments.get_payment_status(doc.name, key)
		self.assertEqual(
			set(status.keys()),
			{"signup_status", "order_status", "amount", "currency", "is_paid",
			 "is_failed", "renewal_note"},
		)


class TestProvisioningContract(FrappeTestCase):
	def test_it_refuses_an_order_the_gateway_never_confirmed(self):
		"""Phase 6 implements this. The contract it has to keep is the refusal.

		A browser callback is a hint, and provisioning a tenant off a hint is how you give
		one away - so an order with no webhook-confirmed transaction provisions nothing.
		"""
		order = frappe.get_doc(
			{"doctype": "Payment Order", "name": "PORD-UNCONFIRMED", "status": "Paid"}
		)
		order.name = "PORD-UNCONFIRMED"
		self.assertFalse(payments.order_is_provisionable(order))
		self.assertIsNone(payments.trigger_provisioning(order))

	def test_its_docstring_still_states_the_contract(self):
		doc = (payments.trigger_provisioning.__doc__ or "").lower()
		self.assertIn("idempotent", doc)
		self.assertIn("webhook", doc)

	def test_a_missing_implementation_does_not_break_a_paid_payment(self):
		order = frappe.get_doc({"doctype": "Payment Order", "name": "PORD-TEST"})
		order.name = "PORD-TEST"
		self.assertIsNone(payments._safely_trigger_provisioning(order))


class TestPaymentSettingsGuards(FrappeTestCase):
	def tearDown(self):
		frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Test")
		frappe.db.set_single_value("A3 Sola Settings", "pre_debit_notice_hours", 24)
		frappe.clear_cache()

	def test_live_mode_without_credentials_is_refused(self):
		settings = frappe.get_single("A3 Sola Settings")
		settings.gateway_mode = "Live"
		settings.razorpay_key_id = None
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)

	def test_a_pre_debit_notice_under_24_hours_is_refused(self):
		"""Debiting without the required notice is a compliance breach, not a setting."""
		settings = frappe.get_single("A3 Sola Settings")
		settings.pre_debit_notice_hours = 6
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)

	def test_24_hours_is_accepted(self):
		settings = frappe.get_single("A3 Sola Settings")
		settings.pre_debit_notice_hours = 24
		settings.save(ignore_permissions=True)
		self.assertEqual(settings.pre_debit_notice_hours, 24)

	def test_payment_postings_default_off(self):
		field = frappe.get_meta("A3 Sola Settings").get_field("enable_payment_postings")
		self.assertIn(field.default, (None, "", "0"))

	def test_the_afa_ceiling_and_notice_have_the_documented_defaults(self):
		meta = frappe.get_meta("A3 Sola Settings")
		self.assertEqual(meta.get_field("afa_free_debit_ceiling").default, "15000")
		self.assertEqual(meta.get_field("pre_debit_notice_hours").default, "24")

	def test_the_credential_fields_are_stored_encrypted(self):
		"""A Data field would put the secret in a plain column and in every export."""
		meta = frappe.get_meta("A3 Sola Settings")
		for fieldname in ("razorpay_key_secret", "razorpay_webhook_secret"):
			self.assertEqual(meta.get_field(fieldname).fieldtype, "Password")

	def test_the_credential_fields_sit_at_permlevel_one(self):
		meta = frappe.get_meta("A3 Sola Settings")
		for fieldname in (
			"razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret",
		):
			self.assertEqual(meta.get_field(fieldname).permlevel, 1, fieldname)


class TestGuestCannotReachPayments(FrappeTestCase):
	"""A Payment Order readable by a logged-out visitor would be a serious breach."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_has_no_permission_on_any_payment_doctype(self):
		from a3_sola.registry import platform as registry

		for doctype in registry.PAYMENT_DOCTYPES:
			meta = frappe.get_meta(doctype)
			for row in meta.permissions:
				if row.role != "Guest":
					continue
				for ptype in ("read", "write", "create", "delete", "submit", "cancel"):
					self.assertFalse(row.get(ptype), f"Guest has {ptype} on {doctype}")

	def test_guest_cannot_list_payment_orders(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Payment Order", ignore_permissions=False)

	def test_guest_cannot_list_payment_transactions(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Payment Transaction", ignore_permissions=False)


class TestMockGatewayMode(PaymentTestCase):
	"""Mock mode lets the whole funnel be walked without a Razorpay account.

	Its danger is obvious - a simulated payment path reachable on a real site would let
	anyone mark themselves paid - so the gate is checked server-side on every call.
	"""

	def test_mock_mode_follows_the_setting(self):
		frappe.flags.in_test = False
		try:
			frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Mock")
			frappe.clear_cache()
			self.assertTrue(razorpay_client.mock_mode())

			frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Test")
			frappe.clear_cache()
			self.assertFalse(razorpay_client.mock_mode())
		finally:
			frappe.flags.in_test = True
			frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Test")
			frappe.clear_cache()

	def test_the_simulated_endpoint_is_refused_off_mock_mode(self):
		"""On a Test or Live site it must behave as though it does not exist."""
		doc, key = self._verified_signup(work_email="mockguard@epc.example")
		payments.initiate_payment(doc.name, key)

		frappe.flags.in_test = False
		frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Live")
		frappe.clear_cache()
		try:
			with self.assertRaises(frappe.DoesNotExistError):
				payments.complete_mock_payment(doc.name, key)
		finally:
			frappe.flags.in_test = True
			frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Test")
			frappe.clear_cache()

	def test_a_simulated_success_marks_everything_paid(self):
		doc, key = self._verified_signup(work_email="mockpay@epc.example")
		payments.initiate_payment(doc.name, key)
		result = payments.complete_mock_payment(doc.name, key, outcome="success")
		self.assertEqual(result["status"], "paid")
		doc.reload()
		self.assertEqual(doc.status, "Paid")

	def test_a_simulated_failure_records_a_failed_attempt(self):
		doc, key = self._verified_signup(work_email="mockfail@epc.example")
		payments.initiate_payment(doc.name, key)
		result = payments.complete_mock_payment(doc.name, key, outcome="failure")
		self.assertEqual(result["status"], "failed")
		doc.reload()
		self.assertEqual(doc.status, "Payment Failed")

	def test_it_still_needs_the_customers_own_key(self):
		doc, key = self._verified_signup(work_email="mockkey@epc.example")
		payments.initiate_payment(doc.name, key)
		with self.assertRaises(frappe.DoesNotExistError):
			payments.complete_mock_payment(doc.name, "not-the-key")

	def test_a_simulated_payment_goes_through_the_real_code_path(self):
		"""Otherwise Mock mode would prove nothing about the real flow."""
		import inspect

		source = inspect.getsource(payments.complete_mock_payment)
		self.assertIn("apply_successful_payment", source)
		self.assertIn("record_failure", source)

	def test_mock_mode_needs_no_credentials(self):
		frappe.flags.in_test = False
		try:
			frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Mock")
			frappe.db.set_single_value("A3 Sola Settings", "razorpay_key_id", "")
			frappe.clear_cache()
			settings = frappe.get_single("A3 Sola Settings")
			settings.save(ignore_permissions=True)
			self.assertIsInstance(
				razorpay_client.get_client(), razorpay_client.MockRazorpayClient
			)
		finally:
			frappe.flags.in_test = True
			frappe.db.set_single_value("A3 Sola Settings", "gateway_mode", "Test")
			frappe.clear_cache()


class TestTheCeilingIsMeasuredOnTheActualDebit(PaymentTestCase):
	"""The RBI ceiling applies to the debit INCLUDING tax, not the sticker price.

	A plan at 13,600 is under a 15,000 ceiling; the same plan actually debits 16,048 with
	GST, which is not. Classifying on the pre-tax figure would promise a customer an
	automatic debit their bank would refuse.
	"""

	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.clear_cache()

	def test_a_pre_tax_recurring_amount_under_the_ceiling_can_still_exceed_it(self):
		doc, key = self._verified_signup(work_email="ceilingtax@epc.example")
		# A recurring subtotal under the ceiling that crosses it once GST is added, with
		# no implementation fee muddying the comparison.
		frappe.db.set_value(
			"Subscription Signup", doc.name,
			{"subtotal": 13600, "tax_amount": 0, "total_amount": 13600,
			 "implementation_fee": 0},
			update_modified=False,
		)
		doc.reload()

		recurring = payments.recurring_amount_of(doc)
		self.assertLess(flt(doc.subtotal, 2), 15000.00, "the pre-tax figure is under")
		self.assertGreater(flt(recurring, 2), 15000.00, "the real debit is over")

		order = payments.build_order_from_signup(doc)
		self.assertIn(
			"above the RBI", order.collection_reason,
			"the route was decided on the pre-tax amount",
		)

	def test_the_one_off_implementation_fee_does_not_decide_the_recurring_route(self):
		"""It is charged once and never debited again."""
		doc, _key = self._verified_signup(work_email="implfee@epc.example")
		self.assertGreater(
			flt(doc.implementation_fee, 2), 0.00, "this test needs a fee to exclude"
		)
		recurring = payments.recurring_amount_of(doc)
		self.assertLess(
			flt(recurring, 2), flt(doc.subtotal, 2),
			"the implementation fee is still inside the recurring figure",
		)
		order = payments.build_order_from_signup(doc)
		self.assertIn("within the RBI ceiling", order.collection_reason)

	def test_the_mandate_records_the_tax_inclusive_debit(self):
		doc, key = self._verified_signup(work_email="mandatetax@epc.example")
		result = payments.initiate_payment(doc.name, key)
		order = frappe.get_doc("Payment Order", result["payment_order"])
		mandate = frappe.db.get_value(
			"Payment Mandate", {"subscription_signup": doc.name},
			["recurring_debit_amount", "registered_max_amount"], as_dict=True,
		)
		if not mandate:
			self.skipTest("this plan routes to assisted renewal, so no mandate is registered")
		self.assertEqual(
			flt(mandate.recurring_debit_amount, 2), flt(payments.recurring_amount_of(doc), 2),
			"the mandate was registered for the wrong amount",
		)
		self.assertGreater(
			flt(mandate.registered_max_amount, 2), flt(payments.recurring_amount_of(doc), 2),
			"the mandate has no headroom above the recurring debit",
		)

	def test_the_order_total_is_the_subtotal_plus_tax(self):
		doc, key = self._verified_signup(work_email="ordertax@epc.example")
		order = payments.build_order_from_signup(doc)
		self.assertEqual(
			flt(order.total_amount, 2),
			flt(flt(order.subtotal) + flt(order.tax_amount), 2),
		)
		self.assertGreater(flt(order.tax_amount, 2), 0.00, "GST was not applied at all")
