# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Collecting the first payment.

============================ THE RULE THIS FILE EXISTS FOR ============================

**Charge the snapshot.** Phase 4 froze the price onto the Subscription Signup at the
moment the applicant agreed to it. Every amount sent to the gateway comes from those
fields. Nothing here calls `calculate_plan_total` - if marketing changes a plan price
this afternoon, a signup from this morning is still charged this morning's number.

=======================================================================================

Two other things worth knowing before changing anything:

* **The browser callback is a hint; the webhook is truth.** `verify_checkout_payment` is
  a convenience path so the customer sees a result immediately. P5-A3S-002's webhook
  handler must reach the identical end state on its own, because a customer who closes
  the tab after paying still has to end up Paid.
* **Every public endpoint here is idempotent.** A replayed callback changes nothing, and
  a double-clicked "Pay" produces one order, guaranteed by a deterministic idempotency
  key rather than by hoping.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_url, now_datetime, today

from a3_sola.api import platform as platform_api
from a3_sola.api import tax
from a3_sola.api.gateways.exceptions import GatewayError
from a3_sola.api.gateways.razorpay_client import (
	get_client,
	redact,
	verify_payment_signature,
)
from a3_sola.api.ratelimit import client_ip, rate_limited
from a3_sola.api.settings import get_float, get_int, get_value

#: What a customer is told when the gateway itself is unhappy. Never the gateway's own
#: message - that can carry account identifiers.
GATEWAY_UNAVAILABLE = (
	"We could not reach the payment gateway just now. Nothing has been charged. "
	"Please try again in a moment."
)


# ------------------------------------------------------------------ classification
def classify_collection(total_amount, billing_cycle):
	"""Decide how this amount can legally be collected, and say why in plain English.

	The RBI e-mandate framework allows a recurring debit without per-cycle
	authentication only up to a ceiling, measured on the TOTAL debit including tax. Above
	it, every debit needs Additional Factor Authentication, so a silent auto-debit is not
	available and the customer must authenticate each cycle.

	Annual always routes to an assisted renewal regardless of amount: annual figures under
	this pricing sit above the ceiling anyway, and a mandate asked to fire twelve months
	later fails at the bank often enough that pretending otherwise just loses the renewal.

	The ceiling is a setting, not a constant - the RBI has revised it repeatedly.
	"""
	ceiling = flt(get_float("afa_free_debit_ceiling", 15000.0))
	amount = flt(total_amount, 2)

	if (billing_cycle or "").lower() == "annual":
		return "Payment Link", _(
			"Annual billing is collected with an authenticated payment link each year. "
			"An annual amount is above the RBI ceiling for silent auto-debit, and a "
			"mandate asked to fire a year later frequently fails at the bank."
		)
	if amount > ceiling:
		return "Payment Link", _(
			"This debit of {0} is above the RBI no-authentication ceiling of {1}, so it "
			"needs your authentication each time rather than an automatic debit."
		).format(frappe.utils.fmt_money(amount, currency="INR"),
		         frappe.utils.fmt_money(ceiling, currency="INR"))
	return "Auto Debit", _(
		"This debit of {0} is within the RBI ceiling of {1}, so it can be collected "
		"automatically once you authorise it the first time."
	).format(frappe.utils.fmt_money(amount, currency="INR"),
	         frappe.utils.fmt_money(ceiling, currency="INR"))


def idempotency_key(reference_doctype, reference_name, order_type, period_start=None):
	"""Deterministic from the thing being billed and the period it covers.

	Two clicks a second apart produce the same key, so the second finds the first order
	instead of creating a second one. The daily billing engine in P5-A3S-002 relies on
	the same property to guarantee it cannot charge one period twice.
	"""
	basis = f"{reference_doctype}|{reference_name}|{order_type}|{period_start or ''}"
	return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:40]


# ------------------------------------------------------------------- order build
def build_order_from_signup(signup, order_type="Initial Subscription"):
	"""A Payment Order copied from the signup's snapshot. Idempotent."""
	key = idempotency_key("Subscription Signup", signup.name, order_type)
	existing = frappe.db.get_value("Payment Order", {"idempotency_key": key}, "name")
	if existing:
		return frappe.get_doc("Payment Order", existing)

	# The RBI ceiling applies to the DEBIT INCLUDING TAX, not the sticker price, so the
	# tax has to be computed before the route can be decided.
	state_code = signup.state and tax.state_code_for(signup.state)
	split = tax.compute_tax(signup.subtotal, state_code)
	tax_amount = flt(signup.tax_amount or split["total_tax"], 2)
	gross = flt(flt(signup.subtotal) + tax_amount, 2)

	# The first payment is always taken through checkout. What is being classified here is
	# how RENEWALS will be collected - so the one-off implementation fee is excluded. It is
	# charged once and never debited again, and letting it decide the recurring route would
	# push customers to assisted renewal over a fee they will never pay twice.
	recurring_gross = recurring_amount_of(signup, state_code)
	mode, reason = classify_collection(recurring_gross, signup.billing_cycle)

	order = frappe.get_doc(
		{
			"doctype": "Payment Order",
			"reference_doctype": "Subscription Signup",
			"reference_name": signup.name,
			"subscription_signup": signup.name,
			"customer_name": signup.full_name,
			"customer_email": signup.work_email,
			"customer_phone": signup.phone,
			"order_type": order_type,
			"billing_cycle": signup.billing_cycle,
			"description": _("{0} plan, billed {1}").format(
				signup.plan_code, (signup.billing_cycle or "").lower()
			),
			"period_start": frappe.utils.today(),
			"period_end": _period_end(signup.billing_cycle),
			# Straight from the snapshot. Not recomputed.
			"base_amount": signup.base_amount,
			"additional_user_amount": signup.additional_user_amount,
			"implementation_fee": signup.implementation_fee,
			"subtotal": signup.subtotal,
			"tax_amount": tax_amount,
			"total_amount": gross,
			"currency": signup.currency or "INR",
			"price_breakdown": signup.price_breakdown,
			"place_of_supply": signup.state,
			"customer_gstin": signup.gstin,
			"customer_state_code": tax.state_code_for(signup.state),
			"gateway": get_value("payment_gateway") or "Razorpay",
			"collection_mode": "Checkout",
			"collection_reason": reason,
			"expires_on": add_to_date(
				now_datetime(), hours=get_int("payment_link_expiry_hours", 72) or 72
			),
			"idempotency_key": key,
			"created_from_ip": client_ip(),
		}
	)
	order.flags.ignore_permissions = True
	order.insert(ignore_permissions=True)
	return order


def recurring_amount_of(signup, state_code=None):
	"""What this subscription will be debited each cycle, tax included.

	The signup snapshot bundles the one-time implementation fee into the subtotal, because
	that is what the applicant pays today. It is not part of any later cycle, so it comes
	out before the recurring figure is worked out.
	"""
	if state_code is None:
		state_code = signup.state and tax.state_code_for(signup.state)
	recurring_subtotal = flt(flt(signup.subtotal) - flt(signup.implementation_fee), 2)
	split = tax.compute_tax(recurring_subtotal, state_code)
	return flt(recurring_subtotal + split["total_tax"], 2)


def _period_end(billing_cycle):
	from frappe.utils import add_days, add_months, add_years, today

	if (billing_cycle or "").lower() == "annual":
		return add_days(add_years(today(), 1), -1)
	return add_days(add_months(today(), 1), -1)


# ------------------------------------------------------------------ public API
@frappe.whitelist(allow_guest=True)
@rate_limited("initiate_payment_ip", "signup_rate_limit_per_ip_per_hour", 10)
def initiate_payment(signup_reference, token):
	"""Create the gateway order and return exactly what checkout needs.

	Implements the Phase 4 extension point. Returns the public key id, the order id, the
	amount and prefill values - never the key secret, never the verification token, never
	the record.
	"""
	from a3_sola.api.signup import _authorised_signup

	signup = _authorised_signup(signup_reference, token)

	if not signup.is_email_verified:
		frappe.throw(
			_("Please confirm your email address before paying."), title=_("Not Verified Yet")
		)
	if signup.status not in ("Verified", "Awaiting Payment", "Payment Failed"):
		frappe.throw(
			_("This signup is not at the payment step."), title=_("Cannot Pay Now")
		)
	if frappe.db.get_value("Subscription Plan", signup.subscription_plan, "is_custom_pricing"):
		frappe.throw(
			_("This plan is priced with our team and cannot be paid online. We will be in "
			  "touch to arrange it."),
			title=_("Talk to Us Instead"),
		)

	order = build_order_from_signup(signup)

	if not order.gateway_order_id:
		try:
			client = get_client()
			gateway_order = client.create_order(
				amount_in_paise=cint(order.amount_in_paise),
				currency=order.currency,
				receipt=order.name,
				notes={"signup": signup.name, "plan": signup.plan_code},
				capture=bool(get_value("auto_capture_payments")),
			)
		except GatewayError as exc:
			frappe.log_error(
				title="a3_sola: gateway order",
				message=f"{exc.__class__.__name__} creating order for {order.name}: {exc}",
			)
			frappe.throw(_(GATEWAY_UNAVAILABLE), title=_("Payment Unavailable"))

		order.db_set("gateway_order_id", gateway_order.get("id"), update_modified=False)
		order.reload()

	if signup.status != "Awaiting Payment":
		signup.set_status("Awaiting Payment", details=_("Checkout opened."))
		signup.flags.ignore_permissions = True
		signup.save(ignore_permissions=True)

	# Where renewals will auto-debit, the mandate is registered in this same interaction:
	# the customer authenticates once for both, which is what the framework expects.
	register_mandate_with_first_payment(signup, order)

	settings = frappe.get_cached_doc("A3 Sola Settings")
	return {
		"order_id": order.gateway_order_id,
		"payment_order": order.name,
		"key_id": settings.razorpay_key_id,
		"amount": cint(order.amount_in_paise),
		"currency": order.currency,
		"name": settings.product_name or "a3 sola",
		"description": order.description,
		"prefill": {
			"name": order.customer_name,
			"email": order.customer_email,
			"contact": order.customer_phone,
		},
		"notes": {"signup": signup.name},
		"callback_url": get_url(
			f"{platform_api.route('payment-status')}?ref={signup.name}&t={token}"
		),
		"collection_mode_for_renewals": order.collection_mode,
		"renewal_note": order.collection_reason,
	}


@frappe.whitelist(allow_guest=True)
@rate_limited("verify_payment_ip", "signup_rate_limit_per_ip_per_hour", 20)
def verify_checkout_payment(payload):
	"""Handle the browser's success callback.

	A convenience so the customer sees a result at once. It is NOT the source of truth:
	the webhook must reach this same end state on its own. Everything here is idempotent,
	so a replayed callback changes nothing.
	"""
	from a3_sola.api.signup import _authorised_signup, _clean, _payload

	data = _payload(payload)
	signup = _authorised_signup(data.get("signup_reference"), data.get("token"))

	order_id = _clean(data.get("razorpay_order_id"), 60)
	payment_id = _clean(data.get("razorpay_payment_id"), 60)
	signature = _clean(data.get("razorpay_signature"), 200)

	order_name = frappe.db.get_value(
		"Payment Order",
		{"gateway_order_id": order_id, "subscription_signup": signup.name},
		"name",
	)
	if not order_name:
		# A callback for an order that is not this signup's is either a mix-up or an
		# attack. Neither deserves detail in the response.
		frappe.throw(_("We could not match that payment."), frappe.DoesNotExistError)

	order = frappe.get_doc("Payment Order", order_name)
	verified = verify_payment_signature(order_id, payment_id, signature)

	if not verified:
		frappe.logger("a3_sola").warning(
			{"event": "checkout_signature_failed", "order": order.name, "ip": client_ip()}
		)
		record_failure(order, {"id": payment_id}, _("Signature verification failed."))
		frappe.throw(
			_("We could not verify that payment. If money has left your account it will be "
			  "confirmed shortly, or refunded automatically."),
			title=_("Could Not Verify"),
		)

	apply_successful_payment(order, payment_id, "Checkout Callback")
	return {"ok": True, "status": order.status, "next": f"{platform_api.route('payment-status')}?ref={signup.name}"}


def apply_successful_payment(order, payment_id, verification_method):
	"""Move an order and its signup to Paid. Idempotent by design.

	Called from the checkout callback and, in P5-A3S-002, from the webhook. Running it
	twice for the same payment must leave exactly the state it left the first time.
	"""
	if order.status == "Paid":
		return order

	try:
		payment = get_client().fetch_payment(payment_id) if payment_id else {}
	except GatewayError:
		payment = {"id": payment_id, "status": "captured"}

	from a3_sola.platform.doctype.payment_transaction.payment_transaction import (
		PaymentTransaction,
	)

	PaymentTransaction.record(order, payment, True, verification_method, status="Captured")

	order.db_set(
		{
			"status": "Paid",
			"paid_on": now_datetime(),
			"amount_paid": order.total_amount,
			"attempt_count": cint(order.attempt_count) + 1,
		},
		update_modified=False,
	)
	order.reload()

	if order.subscription_signup:
		signup = frappe.get_doc("Subscription Signup", order.subscription_signup)
		if signup.status != "Paid":
			signup.payment_completed_on = now_datetime()
			signup.razorpay_order_id = order.gateway_order_id
			signup.razorpay_payment_id = payment_id
			signup.set_status("Paid", details=_("Payment confirmed via {0}.").format(
				verification_method
			))
			signup.flags.ignore_permissions = True
			signup.save(ignore_permissions=True)

	ensure_subscription(order)
	raise_invoice_for(order)
	_safely_trigger_provisioning(order)
	return order


def ensure_subscription(order):
	"""The Platform Subscription container, created once when the first payment lands.

	Phase 5 owns the container; Phase 7 owns its behaviour. It is created here rather than
	at signup because a signup that never pays should not leave a subscription behind, and
	created here rather than in provisioning because the billing engine needs it whether or
	not a workspace was ever built.

	Idempotent: a renewal finds the existing one and links to it.
	"""
	if order.platform_subscription and frappe.db.exists(
		"Platform Subscription", order.platform_subscription
	):
		return order.platform_subscription
	if not order.subscription_signup:
		return None

	signup = frappe.get_doc("Subscription Signup", order.subscription_signup)
	existing = frappe.db.get_value(
		"Platform Subscription", {"subscription_signup": signup.name, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		order.db_set("platform_subscription", existing, update_modified=False)
		return existing

	state_code = signup.state and tax.state_code_for(signup.state)
	# The RECURRING figure, so the one-off implementation fee never inflates what the
	# billing engine will collect every cycle for the next five years.
	recurring_subtotal = flt(flt(signup.subtotal) - flt(signup.implementation_fee), 2)
	split = tax.compute_tax(recurring_subtotal, state_code)

	subscription = frappe.get_doc(
		{
			"doctype": "Platform Subscription",
			"subscription_signup": signup.name,
			"organisation_name": signup.organisation_name,
			"primary_contact_email": signup.work_email,
			"primary_contact_phone": signup.phone,
			"gstin": signup.gstin,
			"state_code": state_code,
			"place_of_supply": signup.state,
			"subscription_plan": signup.subscription_plan,
			"plan_code": signup.plan_code,
			"billing_cycle": signup.billing_cycle,
			"included_users": cint(signup.total_users) - cint(signup.additional_users),
			"additional_users": cint(signup.additional_users),
			"subtotal": recurring_subtotal,
			"tax_amount": split["total_tax"],
			"currency": signup.currency or "INR",
			"start_date": today(),
			"status": "Pending Payment",
		}
	)
	subscription.flags.ignore_permissions = True
	subscription.insert(ignore_permissions=True)
	subscription.submit()
	order.db_set("platform_subscription", subscription.name, update_modified=False)
	order.reload()
	frappe.logger("a3_sola").info(
		{"event": "subscription_created", "subscription": subscription.name, "signup": signup.name}
	)
	return subscription.name


def raise_invoice_for(order):
	"""One tax invoice per collected payment, and never a second.

	Keyed on the payment order, so a webhook arriving twice cannot produce two invoices -
	which would put a hole in nothing but would put a duplicate in the customer's GST
	return.
	"""
	existing = frappe.db.get_value(
		"Subscription Invoice", {"payment_order": order.name, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return existing

	company = frappe.defaults.get_global_default("company") or (
		frappe.get_all("Company", pluck="name", limit=1) or [None]
	)[0]
	if not company:
		frappe.log_error(
			title="a3_sola: invoice not raised",
			message=f"No company exists, so no tax invoice could be raised for {order.name}.",
		)
		return None

	try:
		invoice = frappe.get_doc(
			{
				"doctype": "Subscription Invoice",
				"platform_subscription": order.platform_subscription,
				"payment_order": order.name,
				"subscription_signup": order.subscription_signup,
				"company": company,
				"customer_legal_name": order.customer_name,
				"customer_gstin": order.customer_gstin,
				"customer_state_code": order.customer_state_code,
				"place_of_supply": order.place_of_supply,
				"invoice_date": frappe.utils.today(),
				"period_start": order.period_start,
				"period_end": order.period_end,
				"billing_cycle": order.billing_cycle,
				"due_date": frappe.utils.today(),
				"payment_status": "Paid",
				"paid_amount": order.total_amount,
				"paid_on": frappe.utils.today(),
				"payment_reference": order.gateway_order_id,
			}
		)
		invoice.flags.ignore_permissions = True
		invoice.insert(ignore_permissions=True)
		invoice.submit()
		return invoice.name
	except Exception:
		# A failure to invoice must not undo a payment that has already succeeded.
		frappe.log_error(frappe.get_traceback(), f"a3_sola: invoice for {order.name}")
		return None


def record_failure(order, payment, description=None):
	"""Log an attempt that did not succeed, without losing the history."""
	from a3_sola.platform.doctype.payment_transaction.payment_transaction import (
		PaymentTransaction,
	)

	PaymentTransaction.record(order, payment or {}, False, "Checkout Callback", status="Failed")
	order.db_set(
		{
			"status": "Failed" if order.status != "Paid" else order.status,
			"attempt_count": cint(order.attempt_count) + 1,
			"last_error_code": (payment or {}).get("error_code"),
			"last_error_description": description or (payment or {}).get("error_description"),
		},
		update_modified=False,
	)
	if order.subscription_signup:
		signup = frappe.get_doc("Subscription Signup", order.subscription_signup)
		if signup.status not in ("Paid", "Provisioning", "Active"):
			signup.set_status(
				"Payment Failed",
				reason=description or (payment or {}).get("error_description"),
			)
			signup.flags.ignore_permissions = True
			signup.save(ignore_permissions=True)


@frappe.whitelist(allow_guest=True)
@rate_limited("payment_status_ip", "signup_rate_limit_per_ip_per_hour", 60)
def get_payment_status(signup_reference, token):
	"""What the polling page needs, and nothing else."""
	from a3_sola.api.signup import _authorised_signup

	signup = _authorised_signup(signup_reference, token)
	order = frappe.db.get_value(
		"Payment Order",
		{"subscription_signup": signup.name},
		["name", "status", "total_amount", "currency", "collection_mode", "collection_reason"],
		as_dict=True,
		order_by="creation desc",
	)
	return {
		"signup_status": signup.status,
		"order_status": (order or {}).get("status"),
		"amount": (order or {}).get("total_amount"),
		"currency": (order or {}).get("currency"),
		"is_paid": signup.status in ("Paid", "Provisioning", "Active"),
		"is_failed": signup.status == "Payment Failed",
		"renewal_note": (order or {}).get("collection_reason"),
	}


# ------------------------------------------------------------ Phase 6 contract
def trigger_provisioning(payment_order):
	"""Turn a confirmed first payment into a workspace. Phase 6 implements this.

	Three refusals sit in front of the work, and each one is here because the opposite
	behaviour gives a tenant away:

	* **Webhook-confirmed only.** The browser callback is signed and therefore not
	  forgeable, but it is sent by the party with an interest in the answer and it arrives
	  before the money settles. The gateway's own webhook is the statement provisioning
	  waits for. `steps.ValidatePayment` enforces this again inside the run, because that
	  is where a manual retry enters.
	* **First payment only.** A renewal must never build a second tenant. The check is on
	  the earliest paid order for the subscription, not on "a paid order".
	* **Idempotent.** Delivery is at-least-once, so this runs again. The orchestrator keys
	  on the subscription, so every repeat finds the same job.

	Enqueued rather than executed: this is called from inside a webhook handler, and a
	fifteen-minute company creation has no business inside an HTTP request.
	"""
	from a3_sola.api.provisioning import orchestrator, steps as provisioning_steps

	if not order_is_provisionable(payment_order):
		return None
	if not provisioning_steps.is_first_payment(payment_order):
		frappe.logger("a3_sola").info(
			{"event": "provisioning_skipped_renewal", "order": payment_order.name}
		)
		return None
	if not payment_order.platform_subscription:
		frappe.logger("a3_sola").info(
			{"event": "provisioning_skipped_no_subscription", "order": payment_order.name}
		)
		return None
	return orchestrator.enqueue(payment_order.platform_subscription, "Payment Webhook")


def order_is_provisionable(order):
	"""Paid, and confirmed by the gateway rather than by the customer's browser."""
	if order.status != "Paid":
		return False
	return bool(
		frappe.db.exists(
			"Payment Transaction",
			{
				"payment_order": order.name,
				"status": ["in", ["Captured", "Authorized"]],
				"verification_method": ["in", ["Webhook", "Gateway Fetch", "Manual Override"]],
			},
		)
	)


def _safely_trigger_provisioning(order):
	"""Provisioning must never break a payment that has already succeeded.

	The money is in. If the workspace cannot be built right now that is an operations
	problem with a runbook, not a reason to fail the transaction the customer just
	completed - so this swallows everything, logs it, and tells sales a human is needed.
	"""
	try:
		return trigger_provisioning(order)
	except NotImplementedError:
		frappe.logger("a3_sola").info({"event": "provisioning_deferred", "order": order.name})
		_notify_sales_to_provision(order)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: provisioning {order.name}")
		_notify_sales_to_provision(order)
	return None


def _notify_sales_to_provision(order):
	recipient = get_value("sales_email")
	if not recipient or frappe.flags.in_test or frappe.flags.in_demo:
		return
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=_("Paid and awaiting setup: {0}").format(order.customer_name),
			message=frappe.render_template(
				"a3_sola/templates/emails/provisioning_pending_internal.html",
				{"order": order, "product_name": get_value("product_name") or "a3 sola",
				 "company_legal_name": get_value("company_legal_name") or "",
				 "sales_email": recipient},
			),
			reference_doctype=order.doctype,
			reference_name=order.name,
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: provisioning notice {order.name}")


# ------------------------------------------------------------------- mandates
def register_mandate_with_first_payment(signup, order):
	"""Create the mandate record alongside the first payment.

	AFA is required at registration AND at the first transaction anyway, so combining
	them is both compliant and one less thing to ask the customer to do. Only for the
	Auto Debit route - an assisted-renewal customer authenticates each cycle, so
	registering a mandate they will never be debited under would be misleading.
	"""
	# Classified on the RECURRING debit, tax included - not this first payment, which
	# carries the one-off implementation fee.
	recurring = recurring_amount_of(signup)
	mode, _reason = classify_collection(recurring, signup.billing_cycle)
	if mode != "Auto Debit":
		return None

	existing = frappe.db.get_value(
		"Payment Mandate", {"subscription_signup": signup.name, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return frappe.get_doc("Payment Mandate", existing)

	mandate = frappe.get_doc(
		{
			"doctype": "Payment Mandate",
			"subscription_signup": signup.name,
			"customer_name": signup.organisation_name,
			"customer_email": signup.work_email,
			"customer_phone": signup.phone,
			"mandate_type": "Card e-Mandate",
			# What the bank will actually be asked for each cycle, tax included.
			"recurring_debit_amount": recurring,
			"registered_on": frappe.utils.today(),
		}
	)
	mandate.flags.ignore_permissions = True
	mandate.insert(ignore_permissions=True)
	mandate.submit()
	frappe.logger("a3_sola").info(
		{"event": "mandate_created", "mandate": mandate.name, "signup": signup.name}
	)
	return mandate


@frappe.whitelist(allow_guest=True)
@rate_limited("cancel_mandate_ip", "signup_rate_limit_per_ip_per_hour", 10)
def cancel_mandate(signup_reference, token, reason=None):
	"""Let a customer cancel their mandate at any time.

	The e-mandate framework requires customers to be able to cancel whenever they choose,
	and requires it to be honoured immediately - so this takes effect at once rather than
	raising a request for somebody to action later.
	"""
	from a3_sola.api.signup import _authorised_signup, _clean

	signup = _authorised_signup(signup_reference, token)
	name = frappe.db.get_value(
		"Payment Mandate",
		{"subscription_signup": signup.name, "status": ["in", ["Active", "Paused"]]},
		"name",
	)
	if not name:
		return {"ok": True, "message": _("There is no active mandate to cancel.")}

	mandate = frappe.get_doc("Payment Mandate", name)
	mandate.set_status(
		"Cancelled",
		reason=_clean(reason, 200) or _("Cancelled by the customer."),
		source="Customer",
	)

	subscription = frappe.db.get_value(
		"Platform Subscription", {"payment_mandate": name}, "name"
	)
	if subscription:
		# Future collections now need the customer's authentication each time, and they
		# must be told that rather than discovering it at the next renewal.
		frappe.db.set_value(
			"Platform Subscription", subscription,
			{"collection_route": "Assisted Renewal",
			 "route_reason": _("The automatic mandate was cancelled by the customer, so "
			                   "each renewal now needs their authentication.")},
			update_modified=False,
		)

	_confirm_cancellation(mandate)
	return {
		"ok": True,
		"message": _(
			"Your automatic payment authorisation has been cancelled. Nothing further will "
			"be debited automatically. We will send you a payment link before each renewal."
		),
	}


def _confirm_cancellation(mandate):
	if frappe.flags.in_test or frappe.flags.in_demo:
		return
	try:
		frappe.sendmail(
			recipients=[mandate.customer_email],
			subject=_("Your automatic payment authorisation is cancelled"),
			message=_(
				"We have cancelled the automatic payment authorisation for {0}. Nothing "
				"further will be debited automatically. Before each renewal we will send "
				"you a link to pay, so your service continues uninterrupted."
			).format(mandate.customer_name),
			reference_doctype=mandate.doctype,
			reference_name=mandate.name,
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: cancellation notice {mandate.name}")


# --------------------------------------------------------------- mock gateway
@frappe.whitelist(allow_guest=True)
@rate_limited("mock_pay_ip", "signup_rate_limit_per_ip_per_hour", 30)
def complete_mock_payment(signup_reference, token, outcome="success"):
	"""Simulate the outcome of a payment. ONLY in Mock mode.

	This exists so the whole funnel can be walked end to end before a Razorpay account
	exists. It is gated on the gateway mode being Mock, checked server-side on every call
	- a client that simply stops sending the parameter cannot reach it, and neither can a
	request to a Test or Live site.

	It deliberately goes through the same `apply_successful_payment` and `record_failure`
	paths as a real payment, so what you see in Mock mode is what the real flow does.
	"""
	from a3_sola.api.gateways.razorpay_client import mock_mode
	from a3_sola.api.signup import _authorised_signup, _clean

	if not mock_mode():
		# Not a 404 by accident: on a real site this endpoint does not exist as far as
		# any caller is concerned.
		frappe.throw(_("Not found"), frappe.DoesNotExistError)

	signup = _authorised_signup(signup_reference, token)
	order_name = frappe.db.get_value(
		"Payment Order",
		{"subscription_signup": signup.name},
		"name",
		order_by="creation desc",
	)
	if not order_name:
		frappe.throw(_("There is no payment to complete."), frappe.DoesNotExistError)

	order = frappe.get_doc("Payment Order", order_name)
	outcome = _clean(outcome, 20).lower()

	if outcome == "failure":
		record_failure(
			order,
			{
				"id": f"pay_mock_{frappe.generate_hash(length=10)}",
				"error_code": "BAD_REQUEST_ERROR",
				"error_description": "Simulated failure: payment declined by the bank.",
				"error_source": "bank",
				"error_reason": "insufficient_funds",
			},
			_("Simulated failure in Mock mode."),
		)
		return {"ok": True, "status": "failed", "mock": True}

	payment_id = f"pay_mock_{frappe.generate_hash(length=10)}"
	apply_successful_payment(order, payment_id, "Manual Fetch")
	return {"ok": True, "status": "paid", "mock": True, "payment_id": payment_id}
