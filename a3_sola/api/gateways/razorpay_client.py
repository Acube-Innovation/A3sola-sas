# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A thin Razorpay wrapper.

Deliberately built on `requests` rather than the razorpay SDK: this app already ships
`requests`, and owning the transport is what lets us set an explicit timeout, bound the
retries, and redact every log line. An SDK would hide all three.

Three rules the whole file exists to enforce:

* **Credentials are resolved per call and never held at module level.** A module-level
  client would keep a secret alive in a worker for its whole life and would silently keep
  using Test keys after somebody switched the site to Live.
* **Nothing sensitive is ever logged.** Bodies are redacted before they reach a log line
  or a stored field - see `redact()`, which is used by the doctypes too.
* **Signature comparison is constant-time.** A byte-by-byte comparison that returns early
  is a timing oracle: an attacker can recover a valid signature one byte at a time.
"""

import hashlib
import hmac
import json
import time

import frappe
from frappe import _

from a3_sola.api.gateways.exceptions import (
	GatewayAuthError,
	GatewayConfigError,
	GatewayNetworkError,
	GatewaySignatureError,
	GatewayValidationError,
)

API_BASE = "https://api.razorpay.com/v1"
TIMEOUT = 30
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 3)

#: Anything matching these keys is replaced before a payload is logged or stored. Card
#: data, contact details and tokens must never land in our database or our logs.
SENSITIVE_KEYS = frozenset(
	{
		"card", "card_id", "token", "token_id", "vpa", "email", "contact", "customer_id",
		"key_secret", "secret", "signature", "password", "auth", "authorization",
		"account_number", "ifsc", "aadhaar", "pan", "cvv", "expiry_month", "expiry_year",
	}
)
REDACTED = "[redacted]"

#: Card fields that are safe to keep, because they identify nothing on their own.
SAFE_CARD_KEYS = ("last4", "network", "type", "issuer")


def redact(value):
	"""Strip anything sensitive from a payload, recursively.

	Used before logging and before storing a gateway response. The card object is not
	dropped wholesale - the last four and the network are what a support conversation
	actually needs, and neither identifies a card.
	"""
	if isinstance(value, dict):
		out = {}
		for key, item in value.items():
			lowered = str(key).lower()
			if lowered == "card" and isinstance(item, dict):
				out[key] = {k: item.get(k) for k in SAFE_CARD_KEYS if item.get(k) is not None}
			elif lowered in SENSITIVE_KEYS:
				out[key] = REDACTED
			else:
				out[key] = redact(item)
		return out
	if isinstance(value, list):
		return [redact(item) for item in value]
	return value


# ------------------------------------------------------------------ signatures
def _hmac_hex(message, secret):
	return hmac.new(
		str(secret).encode("utf-8"), str(message).encode("utf-8"), hashlib.sha256
	).hexdigest()


def verify_payment_signature(order_id, payment_id, signature, secret=None):
	"""Verify a checkout callback signature. Constant-time, always."""
	secret = secret or _secret("razorpay_key_secret")
	if not (order_id and payment_id and signature):
		return False
	expected = _hmac_hex(f"{order_id}|{payment_id}", secret)
	return hmac.compare_digest(expected, str(signature))


def verify_webhook_signature(raw_body, signature, secret=None):
	"""Verify a webhook against the EXACT bytes received.

	`raw_body` must be the untouched request body. Re-serialising the JSON first changes
	whitespace and key order, the signature stops matching, and the next person to debug
	it is tempted to turn verification off.
	"""
	secret = secret or _secret("razorpay_webhook_secret")
	if not (raw_body and signature and secret):
		return False
	if isinstance(raw_body, str):
		raw_body = raw_body.encode("utf-8")
	expected = hmac.new(str(secret).encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, str(signature))


def _secret(fieldname):
	settings = frappe.get_cached_doc("A3 Sola Settings")
	return settings.get_password(fieldname, raise_exception=False) or ""


# --------------------------------------------------------------------- client
class RazorpayClient:
	"""One instance per call. Never cached, never module-level."""

	def __init__(self, key_id=None, key_secret=None, mode=None):
		settings = frappe.get_cached_doc("A3 Sola Settings")
		self.mode = mode or settings.gateway_mode or "Test"
		self.key_id = key_id or settings.razorpay_key_id
		self._key_secret = key_secret or settings.get_password(
			"razorpay_key_secret", raise_exception=False
		)
		if not (self.key_id and self._key_secret):
			raise GatewayConfigError(
				_("Razorpay credentials are not configured. Set them in A3 Sola Settings.")
			)

	# -- transport ---------------------------------------------------------
	def _request(self, method, path, payload=None, params=None):
		import requests

		url = f"{API_BASE}{path}"
		started = time.monotonic()
		last_error = None

		for attempt in range(1, MAX_ATTEMPTS + 1):
			try:
				response = requests.request(
					method,
					url,
					json=payload,
					params=params,
					auth=(self.key_id, self._key_secret),
					timeout=TIMEOUT,
					headers={"Content-Type": "application/json"},
				)
			except Exception as exc:
				last_error = exc
				if attempt < MAX_ATTEMPTS:
					time.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
					continue
				self._log(method, path, "network-error", started, attempt)
				raise GatewayNetworkError(
					_("Could not reach the payment gateway. Please try again."),
					detail=str(exc),
				)

			# A 4xx is our fault, not a blip. Retrying it just wastes the customer's time.
			if response.status_code in (401, 403):
				self._log(method, path, response.status_code, started, attempt)
				raise GatewayAuthError(
					_("The payment gateway rejected our credentials."),
					code=response.status_code,
				)
			if 400 <= response.status_code < 500:
				self._log(method, path, response.status_code, started, attempt)
				raise GatewayValidationError(
					_("The payment gateway rejected the request."),
					code=response.status_code,
					detail=redact(_safe_json(response)),
				)
			if response.status_code >= 500:
				last_error = f"HTTP {response.status_code}"
				if attempt < MAX_ATTEMPTS:
					time.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
					continue
				self._log(method, path, response.status_code, started, attempt)
				raise GatewayNetworkError(
					_("The payment gateway is having trouble. Please try again shortly."),
					code=response.status_code,
				)

			self._log(method, path, response.status_code, started, attempt)
			return _safe_json(response)

		raise GatewayNetworkError(_("The payment gateway did not respond."), detail=str(last_error))

	def _log(self, method, path, status, started, attempt):
		frappe.logger("a3_sola").info(
			{
				"event": "gateway_call",
				"gateway": "razorpay",
				"mode": self.mode,
				"method": method,
				"path": path,
				"status": status,
				"attempt": attempt,
				"ms": int((time.monotonic() - started) * 1000),
			}
		)

	# -- orders ------------------------------------------------------------
	def create_order(self, amount_in_paise, currency, receipt, notes=None, capture=True):
		"""Amount is in the smallest currency unit and must already be an integer."""
		if not isinstance(amount_in_paise, int):
			raise GatewayValidationError(
				_("The gateway amount must be a whole number of paise.")
			)
		return self._request(
			"POST",
			"/orders",
			{
				"amount": amount_in_paise,
				"currency": currency or "INR",
				"receipt": receipt,
				"payment_capture": 1 if capture else 0,
				"notes": notes or {},
			},
		)

	def fetch_order(self, order_id):
		return self._request("GET", f"/orders/{order_id}")

	def fetch_payment(self, payment_id):
		return self._request("GET", f"/payments/{payment_id}")

	def fetch_order_payments(self, order_id):
		"""Every payment attempted against one order.

		A fetched order carries a status but not the payment id that satisfied it, and the
		id is what our records key on - so recovering a dropped webhook needs this second
		call.
		"""
		return self._request("GET", f"/orders/{order_id}/payments")

	def capture_payment(self, payment_id, amount_in_paise, currency="INR"):
		return self._request(
			"POST",
			f"/payments/{payment_id}/capture",
			{"amount": amount_in_paise, "currency": currency},
		)

	# -- payment links -----------------------------------------------------
	def create_payment_link(self, amount_in_paise, currency, description, customer,
	                        reference_id, expire_by=None, notes=None):
		payload = {
			"amount": amount_in_paise,
			"currency": currency or "INR",
			"description": description,
			"reference_id": reference_id,
			"customer": customer,
			"notify": {"sms": False, "email": True},
			"reminder_enable": True,
			"notes": notes or {},
		}
		if expire_by:
			payload["expire_by"] = int(expire_by)
		return self._request("POST", "/payment_links", payload)

	def fetch_payment_link(self, link_id):
		return self._request("GET", f"/payment_links/{link_id}")


def _safe_json(response):
	try:
		return response.json()
	except Exception:
		return {"raw": (response.text or "")[:500]}


# ----------------------------------------------------------------- mock client
class MockRazorpayClient(RazorpayClient):
	"""Deterministic fixtures for tests. NO TEST MAY REACH THE REAL API.

	Behaviour is steered by `frappe.flags.mock_gateway_behaviour`:
	"success" (default), "failed", "pending", "auth-error", or "network-error".
	Anything other than "success" is treated as not-yet-paid by the fetch methods.
	"""

	def __init__(self, key_id=None, key_secret=None, mode=None):
		# Deliberately does not call super().__init__: the mock must work on a site with
		# no credentials configured, which is exactly the state a test site is in.
		self.mode = mode or "Test"
		self.key_id = key_id or "rzp_test_mock"
		self._key_secret = key_secret or "mock_secret"
		self.calls = []

	def _behaviour(self):
		return getattr(frappe.flags, "mock_gateway_behaviour", None) or "success"

	def _request(self, method, path, payload=None, params=None):
		self.calls.append({"method": method, "path": path})
		behaviour = self._behaviour()
		if behaviour == "network-error":
			raise GatewayNetworkError(_("Mock network failure."))
		if behaviour == "auth-error":
			raise GatewayAuthError(_("Mock auth failure."))
		return {"mock": True, "method": method, "path": path}

	def create_order(self, amount_in_paise, currency, receipt, notes=None, capture=True):
		if not isinstance(amount_in_paise, int):
			raise GatewayValidationError(_("The gateway amount must be a whole number of paise."))
		self._request("POST", "/orders")
		suffix = hashlib.sha1(str(receipt).encode()).hexdigest()[:14]
		return {
			"id": f"order_{suffix}",
			"entity": "order",
			"amount": amount_in_paise,
			"amount_paid": 0,
			"amount_due": amount_in_paise,
			"currency": currency or "INR",
			"receipt": receipt,
			"status": "created",
			"notes": notes or {},
		}

	def fetch_order(self, order_id):
		self._request("GET", f"/orders/{order_id}")
		paid = self._behaviour() == "success"
		return {
			"id": order_id,
			"entity": "order",
			"status": "paid" if paid else "created",
			"amount_paid": 100 if paid else 0,
		}

	def fetch_payment(self, payment_id):
		self._request("GET", f"/payments/{payment_id}")
		behaviour = self._behaviour()
		status = {"success": "captured", "failed": "failed", "pending": "authorized"}.get(
			behaviour, "captured"
		)
		out = {
			"id": payment_id,
			"entity": "payment",
			"status": status,
			"method": "card",
			"amount": 354000,
			"currency": "INR",
			"fee": 8354,
			"tax": 1274,
			# Deliberately present so the redaction tests have something to strip.
			"email": "someone@example.com",
			"contact": "+919847012345",
			"card": {
				"last4": "1111",
				"network": "Visa",
				"type": "credit",
				"issuer": "HDFC",
				"number": "4111111111111111",
			},
		}
		if status == "failed":
			out.update(
				{
					"error_code": "BAD_REQUEST_ERROR",
					"error_description": "Payment failed due to insufficient funds.",
					"error_source": "bank",
					"error_step": "payment_authorization",
					"error_reason": "insufficient_funds",
				}
			)
		return out

	def fetch_order_payments(self, order_id):
		self._request("GET", f"/orders/{order_id}/payments")
		if self._behaviour() != "success":
			return {"entity": "collection", "count": 0, "items": []}
		suffix = hashlib.sha1(str(order_id).encode()).hexdigest()[:14]
		return {
			"entity": "collection",
			"count": 1,
			"items": [
				{
					"id": f"pay_{suffix}",
					"entity": "payment",
					"status": "captured",
					"amount": 354000,
					"currency": "INR",
					"method": "card",
				}
			],
		}

	def capture_payment(self, payment_id, amount_in_paise, currency="INR"):
		self._request("POST", f"/payments/{payment_id}/capture")
		return {"id": payment_id, "status": "captured", "amount": amount_in_paise}

	def create_payment_link(self, amount_in_paise, currency, description, customer,
	                        reference_id, expire_by=None, notes=None):
		self._request("POST", "/payment_links")
		suffix = hashlib.sha1(str(reference_id).encode()).hexdigest()[:14]
		return {
			"id": f"plink_{suffix}",
			"short_url": f"https://rzp.io/i/{suffix}",
			"amount": amount_in_paise,
			"currency": currency or "INR",
			"status": "created",
			"reference_id": reference_id,
		}

	def fetch_payment_link(self, link_id):
		self._request("GET", f"/payment_links/{link_id}")
		return {"id": link_id, "status": "paid" if self._behaviour() == "success" else "created"}


def mock_mode():
	"""Is this site running the simulated gateway?

	Read fresh every call rather than cached, so switching the mode takes effect at once
	and cannot leave a worker quietly still mocking after somebody went Live.
	"""
	if frappe.flags.in_test or getattr(frappe.flags, "use_mock_gateway", False):
		return True
	try:
		return frappe.db.get_single_value("A3 Sola Settings", "gateway_mode") == "Mock"
	except Exception:
		return False


def get_client():
	"""The only way to obtain a client.

	Returns the mock under tests, and on a site deliberately set to Mock mode, so no test
	can reach the live API by forgetting to patch something and no demo can accidentally
	charge a real card.
	"""
	if mock_mode():
		return MockRazorpayClient()
	return RazorpayClient()
