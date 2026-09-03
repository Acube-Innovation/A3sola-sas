# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Webhooks and recurring collection.

The webhook is the source of truth, so these tests attack it the way reality does:
replayed events, events out of order, events for things that do not exist, and a
tampered body. Every one must converge to the right state or refuse safely.

The compliance tests are not optional either. A debit without a timely pre-debit notice
is a breach of the RBI e-mandate framework, and there is a test asserting the engine
refuses to make one.
"""

import hashlib
import hmac
import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, flt, now_datetime, set_request, today

from a3_sola.api import billing_engine, payments, ratelimit, webhooks
from a3_sola.api.gateways import razorpay_client

WEBHOOK_SECRET = "test_webhook_secret"


def signed(payload, secret=WEBHOOK_SECRET):
	body = json.dumps(payload).encode("utf-8")
	signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
	return body, signature


def event(event_type, payment=None, order=None, token=None, link=None, event_id=None):
	payload = {"event": event_type, "payload": {}}
	if payment:
		payload["payload"]["payment"] = {"entity": payment}
	if order:
		payload["payload"]["order"] = {"entity": order}
	if token:
		payload["payload"]["token"] = {"entity": token}
	if link:
		payload["payload"]["payment_link"] = {"entity": link}
	if event_id:
		payload["id"] = event_id
	return payload


class WebhookTestCase(FrappeTestCase):
	def setUp(self):
		ratelimit.reset_all()
		frappe.flags.mock_gateway_behaviour = "success"
		settings = frappe.get_single("A3 Sola Settings")
		settings.razorpay_webhook_secret = WEBHOOK_SECRET
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		frappe.clear_cache()
		frappe.db.delete("Payment Webhook Log", {"event_id": ["like", "evt_test%"]})

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.set_user("Administrator")

	def post(self, payload, secret=WEBHOOK_SECRET, event_id=None):
		"""Deliver a webhook the way the gateway does: raw bytes plus a signature."""
		body, signature = signed(payload, secret)
		set_request(method="POST", path="/api/method/a3_sola.api.webhooks.receive")
		frappe.local.request._cached_data = body
		frappe.local.request.get_data = lambda *a, **k: body
		frappe.local.request.headers = dict(frappe.local.request.headers or {})
		frappe.local.request.headers["X-Razorpay-Signature"] = signature
		if event_id:
			frappe.local.request.headers["X-Razorpay-Event-Id"] = event_id
		return webhooks.receive()


class TestSignatureIsTheGate(WebhookTestCase):
	def test_a_valid_signature_is_accepted_and_logged(self):
		payload = event("payment.captured", payment={"id": "pay_a", "order_id": "order_a"})
		self.post(payload, event_id="evt_test_1")
		log = frappe.db.get_value(
			"Payment Webhook Log", {"event_id": "evt_test_1"},
			["signature_verified", "processing_status"], as_dict=True,
		)
		self.assertTrue(log.signature_verified)

	def test_a_tampered_body_is_rejected(self):
		payload = event("payment.captured", payment={"id": "pay_b", "order_id": "order_b"})
		body, signature = signed(payload)
		tampered = json.loads(body)
		tampered["payload"]["payment"]["entity"]["amount"] = 1
		tampered_body = json.dumps(tampered).encode()

		set_request(method="POST", path="/api/method/a3_sola.api.webhooks.receive")
		frappe.local.request.get_data = lambda *a, **k: tampered_body
		frappe.local.request.headers = dict(frappe.local.request.headers or {})
		frappe.local.request.headers["X-Razorpay-Signature"] = signature
		webhooks.receive()

		self.assertFalse(
			frappe.db.exists("Payment Webhook Log", {"event_id": "evt_test_tampered"}),
		)
		unverified = frappe.get_all(
			"Payment Webhook Log",
			filters={"signature_verified": 0},
			fields=["raw_payload"], limit=1, order_by="creation desc",
		)
		self.assertTrue(unverified, "the attempt should still be recorded")
		self.assertFalse(
			unverified[0].raw_payload,
			"an unverified body is attacker-controlled and must not be stored",
		)

	def test_an_unverified_event_still_returns_200(self):
		"""A 401 tells an attacker their signature was wrong. Silence tells them nothing."""
		payload = event("payment.captured", payment={"id": "pay_c"})
		result = self.post(payload, secret="wrong_secret")
		self.assertEqual(result["status"], "ok")
		self.assertEqual(frappe.local.response.get("http_status_code"), 200)

	def test_verification_cannot_be_switched_off(self):
		import inspect

		source = inspect.getsource(webhooks.receive)
		self.assertIn("verify_webhook_signature", source)
		# No setting may bypass it.
		self.assertNotIn("skip_signature", source)
		self.assertNotIn("verify_webhooks", source)

	def test_the_raw_body_is_read_before_parsing(self):
		import inspect

		source = inspect.getsource(webhooks.receive)
		raw_at = source.index("_raw_body()")
		parse_at = source.index("frappe.parse_json")
		self.assertLess(
			raw_at, parse_at,
			"the signature must be checked against the bytes received, not re-serialised JSON",
		)


class TestIdempotencyAndOrdering(WebhookTestCase):
	def _paid_order(self, suffix="1"):
		from a3_sola.tests.platform.test_payments_core import PaymentTestCase

		helper = PaymentTestCase(methodName="run")
		helper.setUp()
		doc, key = helper._verified_signup(work_email=f"webhook{suffix}@epc.example")
		result = payments.initiate_payment(doc.name, key)
		return doc, frappe.get_doc("Payment Order", result["payment_order"])

	def test_a_replayed_event_processes_once(self):
		doc, order = self._paid_order("replay")
		payload = event(
			"payment.captured",
			payment={"id": "pay_replay_hook", "order_id": order.gateway_order_id},
		)
		self.post(payload, event_id="evt_test_replay")
		second = self.post(payload, event_id="evt_test_replay")
		self.assertTrue(second.get("replay"))
		self.assertEqual(
			frappe.db.count("Payment Webhook Log", {"event_id": "evt_test_replay"}), 1
		)

	def test_captured_arriving_before_order_paid_still_converges(self):
		doc, order = self._paid_order("order")
		captured = event(
			"payment.captured",
			payment={"id": "pay_order_hook", "order_id": order.gateway_order_id},
		)
		self.post(captured, event_id="evt_test_cap")
		log = frappe.db.get_value("Payment Webhook Log", {"event_id": "evt_test_cap"}, "name")
		webhooks.process_event(log)

		order.reload()
		doc.reload()
		self.assertEqual(order.status, "Paid")
		self.assertEqual(doc.status, "Paid")

		# order.paid arriving afterwards must change nothing.
		transactions = frappe.db.count("Payment Transaction", {"payment_order": order.name})
		order_paid = event(
			"order.paid",
			payment={"id": "pay_order_hook", "order_id": order.gateway_order_id},
			order={"id": order.gateway_order_id},
		)
		self.post(order_paid, event_id="evt_test_orderpaid")
		webhooks.process_event(
			frappe.db.get_value("Payment Webhook Log", {"event_id": "evt_test_orderpaid"}, "name")
		)
		order.reload()
		self.assertEqual(order.status, "Paid")
		self.assertEqual(
			frappe.db.count("Payment Transaction", {"payment_order": order.name}), transactions
		)

	def test_a_failure_after_a_success_does_not_undo_it(self):
		"""Gateways do deliver out of order. A late failure must not unpay a paid order."""
		doc, order = self._paid_order("late")
		self.post(
			event("payment.captured",
			      payment={"id": "pay_late_hook", "order_id": order.gateway_order_id}),
			event_id="evt_test_late_ok",
		)
		webhooks.process_event(
			frappe.db.get_value("Payment Webhook Log", {"event_id": "evt_test_late_ok"}, "name")
		)
		self.post(
			event("payment.failed",
			      payment={"id": "pay_late_fail", "order_id": order.gateway_order_id,
			               "error_description": "late failure"}),
			event_id="evt_test_late_fail",
		)
		webhooks.process_event(
			frappe.db.get_value("Payment Webhook Log", {"event_id": "evt_test_late_fail"}, "name")
		)
		order.reload()
		self.assertEqual(order.status, "Paid")

	def test_an_event_for_an_unknown_order_is_ignored_not_crashed(self):
		self.post(
			event("payment.captured",
			      payment={"id": "pay_ghost", "order_id": "order_does_not_exist"}),
			event_id="evt_test_ghost",
		)
		log = frappe.db.get_value("Payment Webhook Log", {"event_id": "evt_test_ghost"}, "name")
		result = webhooks.process_event(log)
		self.assertEqual(result["status"], "processed")
		self.assertEqual(
			frappe.db.get_value("Payment Webhook Log", log, "processing_status"), "Processed"
		)

	def test_an_unsubscribed_event_is_recorded_as_ignored(self):
		self.post(event("invoice.paid", payment={"id": "pay_x"}), event_id="evt_test_unknown")
		log = frappe.db.get_value("Payment Webhook Log", {"event_id": "evt_test_unknown"}, "name")
		result = webhooks.process_event(log)
		self.assertEqual(result["status"], "ignored")

	def test_the_endpoint_returns_before_processing(self):
		"""Slow synchronous processing multiplies the duplicates you then have to absorb."""
		import inspect

		source = inspect.getsource(webhooks.receive)
		self.assertIn("frappe.enqueue", source)

	def test_handlers_are_a_registry_not_an_if_chain(self):
		self.assertIsInstance(webhooks.HANDLERS, dict)
		for required in (
			"payment.captured", "payment.failed", "order.paid", "payment_link.paid",
			"payment_link.expired", "token.confirmed", "token.rejected",
			"refund.processed", "settlement.processed",
		):
			self.assertIn(required, webhooks.HANDLERS, f"{required} has no handler")


class TestMandateClassification(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.db.set_single_value("A3 Sola Settings", "mandate_headroom_percent", 20)
		frappe.clear_cache()

	def _mandate(self, amount, **kwargs):
		values = {
			"doctype": "Payment Mandate",
			"customer_name": "Test Customer",
			"mandate_type": "Card e-Mandate",
			"recurring_debit_amount": amount,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def test_the_registered_maximum_carries_headroom(self):
		"""A mandate registered at exactly the debit breaks when one user is added."""
		mandate = self._mandate(3540)
		self.assertGreater(flt(mandate.registered_max_amount), 3540)
		self.assertEqual(flt(mandate.registered_max_amount), 4300.00)

	def test_afa_is_not_needed_just_below_the_ceiling(self):
		self.assertFalse(self._mandate(14999).requires_afa_per_debit)

	def test_afa_is_needed_just_above_the_ceiling(self):
		self.assertTrue(self._mandate(15001).requires_afa_per_debit)

	def test_the_ceiling_is_snapshotted_at_registration(self):
		"""A later RBI revision must not silently reclassify an existing mandate."""
		mandate = self._mandate(14999)
		self.assertEqual(flt(mandate.afa_ceiling_at_registration), 15000.00)

		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 5000)
		frappe.clear_cache()
		try:
			mandate.reload()
			mandate.save(ignore_permissions=True)
			self.assertEqual(
				flt(mandate.afa_ceiling_at_registration), 15000.00,
				"the snapshot moved when the setting changed",
			)
			self.assertFalse(
				mandate.requires_afa_per_debit,
				"an existing mandate was reclassified by a setting change",
			)
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
			frappe.clear_cache()

	def test_the_reason_is_written_for_a_human(self):
		mandate = self._mandate(15001)
		self.assertIn("above", mandate.classification_reason)
		self.assertNotIn("afa_free_debit_ceiling", mandate.classification_reason)

	def test_covers_answers_whether_a_debit_is_within_what_was_authorised(self):
		mandate = self._mandate(3540)
		self.assertTrue(mandate.covers(4000))
		self.assertFalse(mandate.covers(9000))

	def test_a_rejected_mandate_raises_an_alert(self):
		mandate = self._mandate(3540)
		mandate.submit()
		mandate.set_status("Rejected", reason="Bank declined the registration.")
		mandate.reload()
		self.assertEqual(mandate.status, "Rejected")


class TestSubscriptionRouting(FrappeTestCase):
	def setUp(self):
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.clear_cache()

	def _subscription(self, subtotal, tax_amount, cycle, **kwargs):
		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		values = {
			"doctype": "Platform Subscription",
			"organisation_name": "Test EPC",
			"primary_contact_email": "billing@testepc.example",
			"subscription_plan": plan,
			"billing_cycle": cycle,
			"included_users": 5,
			"subtotal": subtotal,
			"tax_amount": tax_amount,
			"currency": "INR",
			"start_date": today(),
			"current_period_start": today(),
			"current_period_end": add_days(today(), 30),
			"next_billing_date": today(),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def test_a_small_monthly_subscription_auto_debits(self):
		doc = self._subscription(3000, 540, "Monthly")
		self.assertEqual(flt(doc.recurring_amount), 3540.00)
		self.assertEqual(doc.collection_route, "Auto Debit")

	def test_a_large_monthly_subscription_needs_authentication(self):
		doc = self._subscription(60000, 10800, "Monthly")
		self.assertEqual(doc.collection_route, "Assisted Renewal")

	def test_every_annual_subscription_needs_authentication(self):
		"""Regardless of amount - a year-old mandate fails at the bank too often."""
		for subtotal, tax_amount in ((1000, 180), (30000, 5400), (60000, 10800)):
			doc = self._subscription(subtotal, tax_amount, "Annual")
			self.assertEqual(
				doc.collection_route, "Assisted Renewal",
				f"annual at {subtotal} should not auto-debit",
			)

	def test_the_route_reason_explains_itself(self):
		doc = self._subscription(30000, 5400, "Annual")
		self.assertIn("Annual billing", doc.route_reason)

	def test_the_recurring_amount_includes_tax(self):
		"""The ceiling is measured on the debit, not the sticker price."""
		doc = self._subscription(14000, 2520, "Monthly")
		self.assertEqual(flt(doc.recurring_amount), 16520.00)
		self.assertEqual(
			doc.collection_route, "Assisted Renewal",
			"14,000 is under the ceiling but 16,520 is not - tax must count",
		)

	def test_the_phase_seven_extension_points_hand_over_rather_than_decide(self):
		"""Collection knows a payment failed. It does not get to decide what that costs
		the customer - that is the lifecycle policy's job, and these three are the seam.

		Originally these asserted the stubs still raised. Phase 7 implemented them, so the
		property worth holding now is that the seam is still a seam: each one delegates
		into the lifecycle package instead of acting on access itself.
		"""
		import inspect

		from a3_sola.platform.doctype.platform_subscription import platform_subscription

		for name in (
			"on_billing_cycle_completed", "on_payment_failed_final",
			"on_subscription_activated",
		):
			handler = getattr(platform_subscription, name)
			self.assertTrue(handler.__doc__, f"{name} has no contract docstring")
			source = inspect.getsource(handler)
			self.assertIn("a3_sola.api.lifecycle.handlers", source,
			              f"{name} no longer hands over to the lifecycle package")
			self.assertNotIn("enabled", source,
			                 f"{name} is touching user access from the billing side")


class TestPreDebitNoticeIsMandatory(FrappeTestCase):
	"""Debiting without the required advance notice is a compliance breach."""

	def setUp(self):
		frappe.db.set_single_value("A3 Sola Settings", "pre_debit_notice_hours", 24)
		frappe.clear_cache()

	def test_a_cycle_with_no_notice_is_blocked(self):
		cycle = frappe._dict({"notice_sent_on": None})
		self.assertIsNotNone(billing_engine._notice_blocker(cycle, 24))

	def test_a_notice_sent_too_recently_is_blocked(self):
		cycle = frappe._dict({"notice_sent_on": add_to_date(now_datetime(), hours=-2)})
		blocker = billing_engine._notice_blocker(cycle, 24)
		self.assertIsNotNone(blocker)
		self.assertIn("24 hours are required", blocker)

	def test_a_notice_sent_in_time_clears_the_block(self):
		cycle = frappe._dict({"notice_sent_on": add_to_date(now_datetime(), hours=-25)})
		self.assertIsNone(billing_engine._notice_blocker(cycle, 24))

	def test_the_engine_checks_the_blocker_before_charging(self):
		import inspect

		source = inspect.getsource(billing_engine.auto_debit_pass)
		blocker_at = source.index("_notice_blocker")
		charge_at = source.index("_charge_cycle")
		self.assertLess(
			blocker_at, charge_at, "the notice check must run before the charge"
		)

	def test_the_settings_floor_cannot_be_lowered(self):
		settings = frappe.get_single("A3 Sola Settings")
		settings.pre_debit_notice_hours = 1
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)
		frappe.db.set_single_value("A3 Sola Settings", "pre_debit_notice_hours", 24)


class TestNoDoubleCharging(FrappeTestCase):
	def test_the_same_period_produces_the_same_key(self):
		first = payments.idempotency_key(
			"Platform Subscription", "SUB-1", "Renewal", "2026-09-01"
		)
		second = payments.idempotency_key(
			"Platform Subscription", "SUB-1", "Renewal", "2026-09-01"
		)
		self.assertEqual(first, second)

	def _subscription(self):
		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		doc = frappe.get_doc(
			{
				"doctype": "Platform Subscription",
				"organisation_name": "Double Charge Test",
				"primary_contact_email": "double@testepc.example",
				"subscription_plan": plan,
				"billing_cycle": "Monthly",
				"included_users": 5,
				"subtotal": 3000, "tax_amount": 540, "currency": "INR",
				"start_date": today(),
				"current_period_start": today(),
				"current_period_end": add_days(today(), 30),
				"next_billing_date": today(),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def _order(self, subscription, key):
		order = frappe.get_doc(
			{
				"doctype": "Payment Order",
				"reference_doctype": "Platform Subscription",
				"reference_name": subscription.name,
				"platform_subscription": subscription.name,
				"customer_name": subscription.organisation_name,
				"customer_email": subscription.primary_contact_email,
				"order_type": "Renewal", "collection_mode": "Auto Debit",
				"period_start": "2026-09-01", "period_end": "2026-09-30",
				"subtotal": 3000, "tax_amount": 540, "total_amount": 3540,
				"currency": "INR", "idempotency_key": key,
			}
		)
		order.flags.ignore_permissions = True
		order.insert(ignore_permissions=True)
		return order

	def test_two_runs_of_the_daily_job_cannot_charge_twice(self):
		"""Both runs derive the same key, so the database refuses the second order."""
		subscription = self._subscription()
		key = payments.idempotency_key(
			"Platform Subscription", subscription.name, "Renewal", "2026-09-01"
		)
		self._order(subscription, key)
		with self.assertRaises(frappe.exceptions.UniqueValidationError):
			self._order(subscription, key)


class TestWebhookLogHygiene(WebhookTestCase):
	def test_a_stored_payload_carries_no_card_number(self):
		payload = event(
			"payment.captured",
			payment={
				"id": "pay_card", "order_id": "order_card",
				"card": {"number": "4111111111111111", "last4": "1111", "network": "Visa"},
				"email": "someone@example.com",
			},
		)
		self.post(payload, event_id="evt_test_card")
		stored = frappe.db.get_value(
			"Payment Webhook Log", {"event_id": "evt_test_card"}, "raw_payload"
		)
		self.assertNotIn("4111111111111111", stored)
		self.assertNotIn("someone@example.com", stored)
		self.assertIn("1111", stored, "the last four is useful and safe to keep")

	def test_the_signature_header_is_at_permlevel_one(self):
		meta = frappe.get_meta("Payment Webhook Log")
		for fieldname in ("signature_header", "raw_payload"):
			self.assertEqual(meta.get_field(fieldname).permlevel, 1, fieldname)


class TestMandateRegistrationAtCheckout(FrappeTestCase):
	def setUp(self):
		ratelimit.reset_all()
		frappe.flags.mock_gateway_behaviour = "success"
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.clear_cache()
		frappe.db.delete("Subscription Signup", {"work_email": ["like", "%@%.example"]})

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.set_user("Administrator")

	def _signup(self, **overrides):
		from a3_sola.tests.platform.test_payments_core import PaymentTestCase

		helper = PaymentTestCase(methodName="run")
		helper.setUp()
		return helper._verified_signup(**overrides)

	def test_an_auto_debit_route_registers_a_mandate(self):
		doc, key = self._signup(work_email="automandate@epc.example")
		payments.initiate_payment(doc.name, key)
		mandate = frappe.db.get_value(
			"Payment Mandate", {"subscription_signup": doc.name}, "name"
		)
		self.assertTrue(mandate, "a monthly Starter should register a mandate")

	def test_an_annual_signup_registers_no_mandate(self):
		"""Assisted renewal authenticates each cycle; a mandate would be misleading."""
		doc, key = self._signup(
			work_email="annualmandate@epc.example", billing_cycle="Annual"
		)
		payments.initiate_payment(doc.name, key)
		self.assertFalse(
			frappe.db.exists("Payment Mandate", {"subscription_signup": doc.name}),
			"an annual signup should not register an auto-debit mandate",
		)

	def test_registering_twice_returns_the_same_mandate(self):
		doc, key = self._signup(work_email="oncemandate@epc.example")
		payments.initiate_payment(doc.name, key)
		payments.initiate_payment(doc.name, key)
		self.assertEqual(
			frappe.db.count("Payment Mandate", {"subscription_signup": doc.name}), 1
		)

	def test_a_customer_can_cancel_at_any_time(self):
		doc, key = self._signup(work_email="cancelmandate@epc.example")
		payments.initiate_payment(doc.name, key)
		name = frappe.db.get_value("Payment Mandate", {"subscription_signup": doc.name}, "name")
		frappe.db.set_value("Payment Mandate", name, "status", "Active", update_modified=False)

		result = payments.cancel_mandate(doc.name, key, reason="No longer needed")
		self.assertTrue(result["ok"])
		self.assertEqual(frappe.db.get_value("Payment Mandate", name, "status"), "Cancelled")
		self.assertEqual(
			frappe.db.get_value("Payment Mandate", name, "cancellation_source"), "Customer"
		)

	def test_cancelling_needs_the_customers_own_key(self):
		doc, _key = self._signup(work_email="guardmandate@epc.example")
		with self.assertRaises(frappe.DoesNotExistError):
			payments.cancel_mandate(doc.name, "not-the-key")

	def test_cancelling_when_there_is_nothing_to_cancel_is_not_an_error(self):
		doc, key = self._signup(
			work_email="nomandate@epc.example", billing_cycle="Annual"
		)
		payments.initiate_payment(doc.name, key)
		result = payments.cancel_mandate(doc.name, key)
		self.assertTrue(result["ok"])
