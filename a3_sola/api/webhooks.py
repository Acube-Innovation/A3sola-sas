# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Gateway webhooks.

=========================== THE GOVERNING PRINCIPLE ===========================

**The browser callback is a hint. The webhook is truth.**

Every payment state transition must be reachable from the webhook alone, must be
idempotent, and must converge to the same end state regardless of the order or the number
of times events arrive. Delivery is at-least-once and out-of-order. Both are normal.

===============================================================================

The order of operations in `receive()` is the security, and it is deliberate:

1. Read the RAW body. Signature verification runs on the exact bytes received - parsing
   and re-serialising first changes whitespace and key order, the signature stops
   matching, and the next person to debug it is tempted to disable verification.
2. Verify the signature, constant-time. On failure return 200 and process nothing:
   a different status code or a slower response tells an attacker their guess was closer.
3. Check the event id. A replay is recorded and dropped.
4. Persist and COMMIT before processing, so a crash leaves evidence to replay from.
5. Return 200 fast; process in the background. A gateway that times out retries, and slow
   synchronous processing multiplies the duplicates you then have to be idempotent about.
"""

import hashlib

import frappe
from frappe import _
from a3_sola.api.permissions import require_role
from frappe.utils import cint, now_datetime

from a3_sola.api.gateways.razorpay_client import redact, verify_webhook_signature

#: Handlers by event name. A dict, not an if-elif chain, so adding an event is one entry
#: and an unknown event is a lookup miss rather than a silent fall-through.
HANDLERS = {}


def handles(*event_types):
	def register(fn):
		for event_type in event_types:
			HANDLERS[event_type] = fn
		return fn

	return register


# --------------------------------------------------------------------- endpoint
@frappe.whitelist(allow_guest=True, methods=["POST"])
def receive():
	"""The single webhook endpoint. Always returns 200."""
	raw_body = _raw_body()
	signature = frappe.get_request_header("X-Razorpay-Signature") or ""
	payload_hash = hashlib.sha256(raw_body or b"").hexdigest()

	verified = verify_webhook_signature(raw_body, signature)
	if not verified:
		_log_unverified(raw_body, signature, payload_hash)
		# 200 regardless. A 401 confirms to an attacker that the endpoint exists and that
		# their signature was wrong; silence tells them nothing.
		frappe.local.response["http_status_code"] = 200
		return {"status": "ok"}

	try:
		payload = frappe.parse_json(raw_body.decode("utf-8") if raw_body else "{}")
	except Exception:
		_log_unverified(raw_body, signature, payload_hash, note="unparseable body")
		frappe.local.response["http_status_code"] = 200
		return {"status": "ok"}

	event_id = frappe.get_request_header("X-Razorpay-Event-Id") or payload.get("id") or payload_hash
	event_type = payload.get("event") or "unknown"

	existing = frappe.db.get_value("Payment Webhook Log", {"event_id": event_id}, "name")
	if existing:
		frappe.db.set_value(
			"Payment Webhook Log", existing, "is_replay", 1, update_modified=False
		)
		frappe.db.commit()
		frappe.local.response["http_status_code"] = 200
		return {"status": "ok", "replay": True}

	log = frappe.get_doc(
		{
			"doctype": "Payment Webhook Log",
			"event_id": event_id,
			"event_type": event_type,
			"gateway": "Razorpay",
			"received_on": now_datetime(),
			"signature_header": signature[:120],
			"signature_verified": 1,
			"payload_hash": payload_hash,
			"processing_status": "Verified",
			"source_ip": _source_ip(),
			"raw_payload": frappe.as_json(redact(payload)),
		}
	)
	log.flags.ignore_permissions = True
	log.insert(ignore_permissions=True)
	# Committed before processing: if the worker dies mid-handler, the evidence survives
	# and the event can be reprocessed rather than lost.
	frappe.db.commit()

	# Not under test. Frappe's `enqueue` still reaches redis during a test run, so a bench
	# worker running alongside the suite picks the event up and processes it concurrently
	# with the test that just posted it - two connections writing the same order, and a
	# flake that only appears when a worker happens to be up. The tests drive
	# `process_event` explicitly, which is what they are asserting on anyway.
	if not frappe.flags.in_test:
		frappe.enqueue(
			"a3_sola.api.webhooks.process_event",
			queue="short",
			job_name=f"a3s-webhook-{log.name}",
			log_name=log.name,
			enqueue_after_commit=True,
		)

	frappe.local.response["http_status_code"] = 200
	return {"status": "ok"}


def _raw_body():
	request = getattr(frappe.local, "request", None)
	if not request:
		return b""
	try:
		return request.get_data() or b""
	except Exception:
		return b""


def _source_ip():
	from a3_sola.api.ratelimit import client_ip

	return client_ip()


def _log_unverified(raw_body, signature, payload_hash, note=None):
	"""Record the attempt without trusting a byte of it."""
	try:
		frappe.get_doc(
			{
				"doctype": "Payment Webhook Log",
				"event_id": f"unverified-{payload_hash[:32]}-{frappe.generate_hash(length=8)}",
				"event_type": note or "unverified",
				"gateway": "Razorpay",
				"received_on": now_datetime(),
				"signature_header": (signature or "")[:120],
				"signature_verified": 0,
				"payload_hash": payload_hash,
				"processing_status": "Ignored",
				"source_ip": _source_ip(),
				# Deliberately not stored. An unverified body is attacker-controlled and
				# has no business in our database.
				"raw_payload": None,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: unverified webhook log")

	frappe.logger("a3_sola").warning(
		{"event": "webhook_signature_failed", "ip": _source_ip(), "hash": payload_hash[:16]}
	)


# ------------------------------------------------------------------ processing
def process_event(log_name):
	"""Run the handler for one logged event. Safe to call again."""
	log = frappe.get_doc("Payment Webhook Log", log_name)
	if log.processing_status == "Processed":
		return {"status": "already-processed"}

	log.db_set(
		{
			"processing_status": "Processing",
			"processing_attempts": cint(log.processing_attempts) + 1,
		},
		update_modified=False,
	)

	handler = HANDLERS.get(log.event_type)
	if not handler:
		# An event we do not act on is not an error - Razorpay sends plenty we did not
		# subscribe to. Recording it makes the next "why did nothing happen" answerable.
		log.db_set(
			{"processing_status": "Ignored", "processed_on": now_datetime()},
			update_modified=False,
		)
		return {"status": "ignored", "event": log.event_type}

	payload = frappe.parse_json(log.raw_payload or "{}")
	lock_key = _lock_key(payload)

	try:
		# Two events for one order must not interleave: a captured and a failed arriving
		# together could otherwise both read "Created" and both write.
		with _order_lock(lock_key):
			result = handler(payload, log)
		log.db_set(
			{
				"processing_status": "Processed",
				"processed_on": now_datetime(),
				"related_doctype": (result or {}).get("doctype"),
				"related_name": (result or {}).get("name"),
			},
			update_modified=False,
		)
		return {"status": "processed", "event": log.event_type}
	except Exception:
		frappe.db.rollback()
		log.reload()
		log.db_set(
			{"processing_status": "Failed", "error_traceback": frappe.get_traceback()},
			update_modified=False,
		)
		frappe.db.commit()
		frappe.log_error(frappe.get_traceback(), f"a3_sola: webhook {log.name}")
		return {"status": "failed", "event": log.event_type}


def _lock_key(payload):
	entity = _entity(payload, "payment") or _entity(payload, "order") or {}
	return entity.get("order_id") or entity.get("id") or "a3s-webhook"


class _order_lock:
	"""A short-lived document lock keyed by the order the event concerns."""

	def __init__(self, key):
		self.key = f"a3s-webhook-{key}"

	def __enter__(self):
		from frappe.utils.background_jobs import get_redis_conn

		try:
			self.conn = get_redis_conn()
			acquired = self.conn.set(self.key, "1", nx=True, ex=60)
			# Not acquiring is not fatal: the handlers are idempotent anyway, and blocking
			# a webhook worker forever would be worse than a rare concurrent run.
			self.held = bool(acquired)
		except Exception:
			self.conn = None
			self.held = False
		return self

	def __exit__(self, *exc):
		if getattr(self, "conn", None) and self.held:
			try:
				self.conn.delete(self.key)
			except Exception:
				pass
		return False


def _entity(payload, kind):
	return ((payload.get("payload") or {}).get(kind) or {}).get("entity") or {}


def _order_for(payload):
	"""Find our Payment Order from whatever the event carries."""
	payment = _entity(payload, "payment")
	order_entity = _entity(payload, "order")
	gateway_order_id = payment.get("order_id") or order_entity.get("id")
	if not gateway_order_id:
		return None
	name = frappe.db.get_value(
		"Payment Order", {"gateway_order_id": gateway_order_id}, "name"
	)
	return frappe.get_doc("Payment Order", name) if name else None


# -------------------------------------------------------------------- handlers
@handles("payment.captured", "order.paid")
def handle_payment_captured(payload, log):
	"""Money is in. Converges to Paid however it arrives, and in whatever order."""
	from a3_sola.api import payments

	order = _order_for(payload)
	if not order:
		return None
	payment = _entity(payload, "payment")
	payments.apply_successful_payment(order, payment.get("id"), "Webhook")
	return {"doctype": "Payment Order", "name": order.name}


@handles("payment.authorized")
def handle_payment_authorized(payload, log):
	"""Authorised but not captured. Records the attempt without claiming the money."""
	order = _order_for(payload)
	if not order:
		return None
	payment = _entity(payload, "payment")
	from a3_sola.platform.doctype.payment_transaction.payment_transaction import (
		PaymentTransaction,
	)

	PaymentTransaction.record(order, payment, True, "Webhook", status="Authorized")
	if order.status in ("Created", "Pending"):
		order.db_set("status", "Attempted", update_modified=False)
	return {"doctype": "Payment Order", "name": order.name}


@handles("payment.failed")
def handle_payment_failed(payload, log):
	from a3_sola.api import payments

	order = _order_for(payload)
	if not order:
		return None
	# A failure arriving after a success must not undo the success. Gateways do send
	# events out of order.
	if order.status == "Paid":
		return {"doctype": "Payment Order", "name": order.name}
	payments.record_failure(order, _entity(payload, "payment"))
	return {"doctype": "Payment Order", "name": order.name}


@handles("payment_link.paid")
def handle_payment_link_paid(payload, log):
	from a3_sola.api import payments

	entity = _entity(payload, "payment_link")
	link_id = entity.get("id")
	name = frappe.db.get_value("Payment Order", {"gateway_payment_link_id": link_id}, "name")
	if not name:
		return None
	order = frappe.get_doc("Payment Order", name)
	payment = _entity(payload, "payment")
	payments.apply_successful_payment(order, payment.get("id"), "Webhook")
	return {"doctype": "Payment Order", "name": order.name}


@handles("payment_link.expired")
def handle_payment_link_expired(payload, log):
	entity = _entity(payload, "payment_link")
	name = frappe.db.get_value(
		"Payment Order", {"gateway_payment_link_id": entity.get("id")}, "name"
	)
	if not name:
		return None
	order = frappe.get_doc("Payment Order", name)
	if order.status not in ("Paid", "Refunded"):
		order.db_set("status", "Expired", update_modified=False)
	return {"doctype": "Payment Order", "name": order.name}


@handles("token.confirmed")
def handle_token_confirmed(payload, log):
	"""The customer authorised the mandate. Now it can be debited."""
	token = _entity(payload, "token")
	mandate = _mandate_for_token(token)
	if not mandate:
		return None
	mandate.db_set(
		{"gateway_token_id": token.get("id"), "registered_on": frappe.utils.today()},
		update_modified=False,
	)
	mandate.reload()
	mandate.set_status("Active", reason=_("Confirmed by the customer's bank."))
	return {"doctype": "Payment Mandate", "name": mandate.name}


@handles("token.rejected")
def handle_token_rejected(payload, log):
	token = _entity(payload, "token")
	mandate = _mandate_for_token(token)
	if not mandate:
		return None
	mandate.set_status(
		"Rejected",
		reason=token.get("error_description") or _("The bank rejected the mandate."),
	)
	return {"doctype": "Payment Mandate", "name": mandate.name}


@handles("token.paused")
def handle_token_paused(payload, log):
	mandate = _mandate_for_token(_entity(payload, "token"))
	if not mandate:
		return None
	mandate.set_status("Paused", reason=_("Paused at the bank."))
	return {"doctype": "Payment Mandate", "name": mandate.name}


@handles("token.cancelled")
def handle_token_cancelled(payload, log):
	mandate = _mandate_for_token(_entity(payload, "token"))
	if not mandate:
		return None
	mandate.set_status("Cancelled", reason=_("Cancelled at the bank."), source="Bank")
	return {"doctype": "Payment Mandate", "name": mandate.name}


def _mandate_for_token(token):
	token_id = (token or {}).get("id")
	name = None
	if token_id:
		name = frappe.db.get_value("Payment Mandate", {"gateway_token_id": token_id}, "name")
	if not name and (token or {}).get("customer_id"):
		name = frappe.db.get_value(
			"Payment Mandate",
			{"gateway_customer_id": token["customer_id"], "status": "Pending Registration"},
			"name",
		)
	return frappe.get_doc("Payment Mandate", name) if name else None


#: Events P5-A3S-003 and 004 attach to. Registered now so an unhandled subscription or
#: refund event is logged as Ignored rather than lost.
for _event in (
	"refund.created", "refund.processed", "refund.failed",
	"subscription.activated", "subscription.charged", "subscription.pending",
	"subscription.halted", "subscription.cancelled", "subscription.completed",
	"settlement.processed",
):
	HANDLERS.setdefault(_event, lambda payload, log: None)


# ------------------------------------------------------------------- retry job
def retry_failed_webhooks():
	"""Daily: reprocess Failed logs with a bounded number of attempts, then alert."""
	limit = 5
	rows = frappe.get_all(
		"Payment Webhook Log",
		filters={"processing_status": "Failed", "processing_attempts": ["<", limit]},
		pluck="name",
		limit_page_length=100,
	)
	for name in rows:
		try:
			process_event(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: webhook retry {name}")

	stuck = frappe.db.count(
		"Payment Webhook Log",
		{"processing_status": "Failed", "processing_attempts": [">=", limit]},
	)
	if stuck:
		frappe.log_error(
			title="a3_sola: webhooks stuck",
			message=f"{stuck} webhook events have failed {limit} times and are no longer being "
			"retried. Each one is a payment state this system has not applied.",
		)
	frappe.logger("a3_sola").info(
		{"event": "webhook_retry_pass", "retried": len(rows), "stuck": stuck}
	)
	return {"retried": len(rows), "stuck": stuck}


@frappe.whitelist()
def reprocess(log_name):
	"""Admin action on a Payment Webhook Log."""
	require_role(
		("Platform Admin", "Platform Billing Manager", "System Manager"),
		_("Reprocessing a webhook"),
	)
	frappe.db.set_value(
		"Payment Webhook Log", log_name, "processing_status", "Verified", update_modified=False
	)
	return process_event(log_name)
