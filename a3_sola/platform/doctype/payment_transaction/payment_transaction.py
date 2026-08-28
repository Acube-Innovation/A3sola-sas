# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One row per payment attempt.

A failed-then-succeeded payment leaves two rows, not one overwritten one - because when a
customer says "it took the money twice" the only useful answer comes from a full history.

`raw_response` is redacted before it is stored. Card numbers, contact details and tokens
must never reach our database, and the place to enforce that is on the way in.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from a3_sola.api.gateways.razorpay_client import redact
from a3_sola.api.naming import set_name


class PaymentTransaction(Document):
	def autoname(self):
		set_name(self, "payment_transaction_series_prefix", ".YYYY.-.#####", fallback="PTXN")

	def validate(self):
		self.redact_raw_response()
		self.trim_method_detail()

	def redact_raw_response(self):
		"""Strip anything sensitive before it is written, not after."""
		if not self.raw_response:
			return
		try:
			payload = frappe.parse_json(self.raw_response)
		except Exception:
			return
		self.raw_response = frappe.as_json(redact(payload))

	def trim_method_detail(self):
		"""Network and last four is all we keep, and all support ever needs."""
		if self.method_detail and len(self.method_detail) > 60:
			self.method_detail = self.method_detail[:60]

	@staticmethod
	def record(order, gateway_payment, verified, verification_method, status=None):
		"""Create an attempt row from a gateway payment payload. Idempotent per payment id."""
		payment_id = (gateway_payment or {}).get("id")
		if payment_id:
			existing = frappe.db.get_value(
				"Payment Transaction", {"gateway_payment_id": payment_id}, "name"
			)
			if existing:
				return frappe.get_doc("Payment Transaction", existing)

		card = (gateway_payment or {}).get("card") or {}
		detail = " ".join(
			str(part) for part in (card.get("network"), card.get("last4")) if part
		) or (gateway_payment or {}).get("bank") or (gateway_payment or {}).get("wallet")

		doc = frappe.get_doc(
			{
				"doctype": "Payment Transaction",
				"payment_order": order.name,
				"attempt_number": (order.attempt_count or 0) + 1,
				"gateway_payment_id": payment_id,
				"method": _method_of(gateway_payment),
				"method_detail": detail,
				"amount": order.total_amount,
				"currency": order.currency,
				"status": status or _status_of(gateway_payment),
				"gateway_fee": _rupees((gateway_payment or {}).get("fee")),
				"gateway_tax": _rupees((gateway_payment or {}).get("tax")),
				"error_code": (gateway_payment or {}).get("error_code"),
				"error_description": (gateway_payment or {}).get("error_description"),
				"error_source": (gateway_payment or {}).get("error_source"),
				"error_step": (gateway_payment or {}).get("error_step"),
				"error_reason": (gateway_payment or {}).get("error_reason"),
				"initiated_on": frappe.utils.now_datetime(),
				"completed_on": frappe.utils.now_datetime(),
				"signature_verified": 1 if verified else 0,
				"verification_method": verification_method,
				"raw_response": frappe.as_json(gateway_payment or {}),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc


def _method_of(payment):
	mapping = {
		"card": "Card", "upi": "UPI", "netbanking": "Netbanking",
		"wallet": "Wallet", "emi": "EMI",
	}
	return mapping.get((payment or {}).get("method"), "Other")


def _status_of(payment):
	mapping = {
		"created": "Created", "authorized": "Authorized", "captured": "Captured",
		"failed": "Failed", "refunded": "Refunded",
	}
	return mapping.get((payment or {}).get("status"), "Created")


def _rupees(paise):
	from a3_sola.api import tax

	return tax.from_paise(paise or 0)
