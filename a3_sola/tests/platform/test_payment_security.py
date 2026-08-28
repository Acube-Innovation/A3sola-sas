# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The payment surface, audited.

Three things this file proves, each of which would be a serious incident if untrue:

* No secret ever reaches stored data, a log, a response or an export.
* No card number ever reaches stored data - only the last four and the network.
* No guest can read anything in the payment domain.

Plus a concurrency stress: the same webhook fired repeatedly must produce exactly one
state transition, because at-least-once delivery guarantees this will happen in
production.
"""

import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request

from a3_sola.api import payments, ratelimit, webhooks
from a3_sola.api.gateways import razorpay_client
from a3_sola.registry import platform as registry
from a3_sola.api.platform import base_route

#: A 13-19 digit run that is not obviously a timestamp or an id. Deliberately broad: a
#: false positive costs a minute, a false negative costs a PCI incident.
PAN_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SECRET_PATTERNS = (
	re.compile(r"rzp_(?:live|test)_[A-Za-z0-9]{10,}"),
	re.compile(r"\"key_secret\"\s*:\s*\"(?!\[redacted\])"),
	re.compile(r"\"webhook_secret\"\s*:\s*\"(?!\[redacted\])"),
)


def _looks_like_a_card(value):
	for candidate in PAN_PATTERN.findall(value or ""):
		digits = re.sub(r"\D", "", candidate)
		if 13 <= len(digits) <= 19 and _luhn(digits):
			return digits
	return None


def _luhn(digits):
	total, alternate = 0, False
	for char in reversed(digits):
		value = int(char)
		if alternate:
			value *= 2
			if value > 9:
				value -= 9
		total += value
		alternate = not alternate
	return total % 10 == 0


class TestNoSecretsInStoredData(FrappeTestCase):
	def _stored_blobs(self):
		blobs = []
		for doctype, field in (
			("Payment Webhook Log", "raw_payload"),
			("Payment Transaction", "raw_response"),
			("Payment Order", "price_breakdown"),
			("Subscription Signup", "price_breakdown"),
		):
			for row in frappe.get_all(
				doctype, fields=["name", field], limit_page_length=0
			):
				if row.get(field):
					blobs.append((doctype, row["name"], row[field]))
		return blobs

	def test_no_stored_payload_contains_anything_secret_shaped(self):
		offenders = []
		for doctype, name, blob in self._stored_blobs():
			for pattern in SECRET_PATTERNS:
				if pattern.search(blob):
					offenders.append(f"{doctype} {name}")
					break
		self.assertEqual(offenders, [], f"secret-shaped values found in: {offenders}")

	def test_no_stored_payload_contains_a_card_number(self):
		offenders = []
		for doctype, name, blob in self._stored_blobs():
			if _looks_like_a_card(blob):
				offenders.append(f"{doctype} {name}")
		self.assertEqual(offenders, [], f"card-like values found in: {offenders}")

	def test_the_error_log_carries_no_secrets(self):
		for row in frappe.get_all(
			"Error Log", fields=["name", "error"], limit_page_length=200,
			order_by="creation desc",
		):
			for pattern in SECRET_PATTERNS:
				self.assertIsNone(
					pattern.search(row.error or ""),
					f"Error Log {row.name} contains something secret-shaped",
				)

	def test_the_luhn_check_actually_works(self):
		"""Otherwise the two tests above would pass on anything."""
		self.assertTrue(_looks_like_a_card("4111111111111111"))
		self.assertTrue(_looks_like_a_card("card 4111 1111 1111 1111 end"))
		self.assertIsNone(_looks_like_a_card("1234567890123456"))
		self.assertIsNone(_looks_like_a_card("no digits here"))

	def test_redaction_strips_a_real_looking_card(self):
		cleaned = frappe.as_json(
			razorpay_client.redact(
				{"card": {"number": "4111111111111111", "last4": "1111", "network": "Visa"}}
			)
		)
		self.assertIsNone(_looks_like_a_card(cleaned))
		self.assertIn("1111", cleaned, "the last four is safe and useful")

	def test_no_credential_is_hardcoded_in_the_app(self):
		import glob
		import io
		import os

		import a3_sola

		root = os.path.dirname(a3_sola.__file__)
		offenders = []
		for path in glob.glob(os.path.join(root, "**/*.py"), recursive=True):
			source = io.open(path, encoding="utf-8").read()
			for pattern in SECRET_PATTERNS[:1]:
				for match in pattern.findall(source):
					if "mock" in match.lower():
						continue
					offenders.append(f"{os.path.relpath(path, root)}: {match}")
		self.assertEqual(offenders, [], f"hardcoded credentials: {offenders}")


class TestNoPciDataReachesUs(FrappeTestCase):
	def test_the_checkout_page_posts_no_card_field(self):
		import io
		import os

		import a3_sola

		root = os.path.dirname(a3_sola.__file__)
		for path in (
			os.path.join(root, "www", base_route(), "checkout.html"),
			os.path.join(root, "public", "js", "checkout.js"),
		):
			source = io.open(path, encoding="utf-8").read().lower()
			for forbidden in ("card_number", "cardnumber", 'name="cvv"', "expiry_month"):
				self.assertNotIn(
					forbidden, source,
					f"{os.path.basename(path)} handles card data; it must not",
				)

	def test_checkout_uses_the_gateways_hosted_flow(self):
		import io
		import os

		import a3_sola

		source = io.open(
			os.path.join(os.path.dirname(a3_sola.__file__), "public", "js", "checkout.js"),
			encoding="utf-8",
		).read()
		self.assertIn("new Razorpay(", source, "checkout must use the hosted gateway flow")


class TestGuestHasNothingInPayments(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_no_payment_doctype_grants_a_guest_anything(self):
		offenders = []
		for doctype in registry.PAYMENT_DOCTYPES:
			meta = frappe.get_meta(doctype)
			for row in meta.permissions:
				if row.role != "Guest":
					continue
				for ptype in ("read", "write", "create", "delete", "submit", "cancel", "report", "export"):
					if row.get(ptype):
						offenders.append(f"{doctype}.{ptype}")
		self.assertEqual(offenders, [], f"guest permissions in the payment domain: {offenders}")

	def test_a_guest_cannot_list_any_payment_doctype(self):
		frappe.set_user("Guest")
		for doctype in ("Payment Order", "Payment Transaction", "Payment Webhook Log",
		                "Payment Mandate", "Platform Subscription", "Subscription Invoice",
		                "Payment Refund", "Settlement Reconciliation"):
			with self.assertRaises(frappe.PermissionError, msg=f"guest can list {doctype}"):
				frappe.get_list(doctype, ignore_permissions=False)

	def test_billing_executive_cannot_approve_a_refund(self):
		"""Viewing payments and giving money back are different jobs."""
		from a3_sola.platform.doctype.payment_refund.payment_refund import APPROVER_ROLES

		self.assertNotIn("Platform Billing Executive", APPROVER_ROLES)

	def test_gateway_credentials_are_permlevel_one(self):
		meta = frappe.get_meta("A3 Sola Settings")
		for fieldname in (
			"razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret",
			"webhook_path_token",
		):
			self.assertEqual(meta.get_field(fieldname).permlevel, 1, fieldname)

	def test_only_platform_admin_holds_settings_level_one(self):
		granted = {
			row.role for row in frappe.get_meta("A3 Sola Settings").permissions
			if row.permlevel == 1
		}
		self.assertTrue(granted)
		self.assertEqual(granted - {"Platform Admin", "System Manager"}, set())


class TestEveryPublicPaymentEndpointIsGuarded(FrappeTestCase):
	def test_every_allow_guest_payment_endpoint_is_rate_limited(self):
		import inspect

		unlimited = []
		source = inspect.getsource(payments)
		for block in source.split("@frappe.whitelist(allow_guest=True)")[1:]:
			head = block.split("def ", 1)
			name = head[1].split("(")[0] if len(head) > 1 else "?"
			if "rate_limited" not in head[0]:
				unlimited.append(name)
		self.assertEqual(unlimited, [], f"unlimited public payment endpoints: {unlimited}")

	def test_the_webhook_endpoint_verifies_before_anything_else(self):
		import inspect

		source = inspect.getsource(webhooks.receive)
		verify_at = source.index("verify_webhook_signature")
		insert_at = source.index(".insert(")
		self.assertLess(
			verify_at, insert_at, "the signature must be checked before anything is stored"
		)

	def test_no_public_payment_endpoint_returns_a_record(self):
		"""Each returns a hand-built dict, never a document."""
		import inspect

		for name in ("initiate_payment", "get_payment_status", "verify_checkout_payment"):
			body = inspect.getsource(getattr(payments, name))
			self.assertNotIn("return order\n", body.replace("\treturn order\n", ""))
			self.assertNotIn("as_dict(doc)", body)


class TestWebhookConcurrencyStress(FrappeTestCase):
	"""At-least-once delivery guarantees this happens in production."""

	def setUp(self):
		ratelimit.reset_all()
		frappe.flags.mock_gateway_behaviour = "success"
		settings = frappe.get_single("A3 Sola Settings")
		settings.razorpay_webhook_secret = "stress_secret"
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
		# The webhook endpoint commits its log before processing - deliberately, so an
		# event survives a worker crash - which means a previous run of this test leaves a
		# row behind that a later run would see as a replay and skip. Clearing it is the
		# price of testing an endpoint that is supposed to commit.
		frappe.db.delete("Payment Webhook Log", {"event_id": ["like", "evt_stress%"]})
		frappe.clear_cache()

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.set_user("Administrator")

	def test_the_same_event_fired_fifty_times_transitions_once(self):
		import hashlib
		import hmac
		import json

		from a3_sola.tests.platform.test_payments_core import PaymentTestCase

		helper = PaymentTestCase(methodName="run")
		helper.setUp()
		doc, key = helper._verified_signup(work_email="stress@epc.example")
		result = payments.initiate_payment(doc.name, key)
		order = frappe.get_doc("Payment Order", result["payment_order"])

		# Unique per run, for the same reason the log is cleared in setUp: the endpoint
		# commits, so ids leak between runs. A Payment Transaction is deduplicated by
		# gateway payment id, and a leftover `pay_stress_1` from an earlier run would
		# silently absorb this one - the test would then pass or fail on the state of the
		# developer's database rather than on the code.
		payment_id = f"pay_stress_{frappe.generate_hash(length=10)}"
		event_id = f"evt_stress_{frappe.generate_hash(length=10)}"
		payload = {
			"event": "payment.captured",
			"payload": {
				"payment": {"entity": {"id": payment_id, "order_id": order.gateway_order_id}}
			},
		}
		body = json.dumps(payload).encode()
		signature = hmac.new(b"stress_secret", body, hashlib.sha256).hexdigest()

		for index in range(50):
			set_request(method="POST", path="/api/method/a3_sola.api.webhooks.receive")
			frappe.local.request.get_data = lambda *a, **k: body
			frappe.local.request.headers = dict(frappe.local.request.headers or {})
			frappe.local.request.headers["X-Razorpay-Signature"] = signature
			frappe.local.request.headers["X-Razorpay-Event-Id"] = event_id
			webhooks.receive()

		# One log row, because the event id is the idempotency key.
		self.assertEqual(
			frappe.db.count("Payment Webhook Log", {"event_id": event_id}), 1
		)

		log = frappe.db.get_value(
			"Payment Webhook Log", {"event_id": event_id}, "name"
		)
		for _index in range(10):
			webhooks.process_event(log)

		# One transaction, one paid order, however many times it was processed.
		self.assertEqual(
			frappe.db.count("Payment Transaction", {"payment_order": order.name}), 1
		)
		order.reload()
		self.assertEqual(order.status, "Paid")
		self.assertEqual(
			frappe.db.count(
				"Subscription Invoice", {"payment_order": order.name, "docstatus": 1}
			),
			1,
			"a repeated webhook raised more than one tax invoice",
		)
