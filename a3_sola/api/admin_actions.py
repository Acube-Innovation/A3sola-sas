# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The buttons an operator presses when a payment has gone sideways.

Payments fail in ways nobody designed for: a webhook is dropped, a gateway times out
after taking the money, a customer's bank calls to say a debit went through that our
records say did not. Without deliberate recovery actions, the person on support ends up
editing rows in the database, which is how money records quietly become fiction.

Each action here follows the same shape, and the shape is the point:

  1. **Check the role.** Not the doctype permission - the specific privilege. Reading a
     Payment Order and overriding one are different powers.
  2. **Prefer the gateway's answer to ours.** Where the gateway can be asked, ask it.
     `refetch_payment_status` exists so an operator can resolve a disagreement with
     evidence instead of judgement.
  3. **Demand a reason for anything the gateway cannot confirm.** `mark_paid_manually`
     asserts a fact no system verified. It requires the operator to say why, in their own
     words, and it records that permanently.
  4. **Write the audit entry.** Before the action where the entry documents intent, after
     where it documents outcome. Never optional.

What is deliberately absent: any action that deletes, back-dates, or silently rewrites a
collected payment. The correction for a wrong payment record is a refund or a cancelled
invoice, both of which leave the original standing.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime, today

from a3_sola.api import audit
from a3_sola.api.permissions import require_role

#: Who may operate the recovery actions at all.
OPERATOR_ROLES = ("Platform Billing Manager", "Platform Admin", "System Manager")

#: Asserting a payment nobody can verify is a higher privilege than the rest.
OVERRIDE_ROLES = ("Platform Admin", "System Manager")

#: Gateway statuses that mean the money is ours, mapped to what we call it.
GATEWAY_PAID = {"paid", "captured", "authorized"}


def _operator():
	# `require_role`, not Frappe's `only_for`: that one returns immediately under test,
	# so a guard written with it is never actually proven by the suite.
	require_role(OPERATOR_ROLES, _("Operating a payment record"))


def _reason(reason, what):
	reason = (reason or "").strip()
	if len(reason) < 10:
		frappe.throw(
			_("Say why you are {0}, in a sentence. This is kept permanently and is what "
			  "an auditor will read.").format(what),
			title=_("A reason is required"),
		)
	return reason[:1000]


# --------------------------------------------------------------- payment order
@frappe.whitelist()
def refetch_payment_status(payment_order):
	"""Ask the gateway what it thinks, and reconcile our record to the answer.

	This is the first thing to try whenever our status and reality disagree, because it
	settles the question with the gateway's own record rather than an operator's opinion.
	It will move an order from Pending to Paid, but it will never move one *out* of Paid:
	if the gateway says unpaid and we say paid, that is a discrepancy for a human, not
	something to silently reverse.
	"""
	_operator()
	from a3_sola.api import payments
	from a3_sola.api.gateways.razorpay_client import get_client
	from a3_sola.api.gateways.exceptions import GatewayError

	order = frappe.get_doc("Payment Order", payment_order)
	if not order.gateway_order_id and not order.gateway_payment_link_id:
		frappe.throw(_("This order was never sent to the gateway, so there is nothing to fetch."))

	client = get_client()
	try:
		if order.gateway_order_id:
			remote = client.fetch_order(order.gateway_order_id)
		else:
			remote = client.fetch_payment_link(order.gateway_payment_link_id)
	except GatewayError as exception:
		frappe.throw(_("The gateway could not be reached: {0}").format(str(exception)))

	remote_status = (remote.get("status") or "").lower()
	remote_paid = remote_status in GATEWAY_PAID or cint(remote.get("amount_paid")) > 0
	payment_id = _payment_id_from(remote, client, order)

	outcome = {
		"gateway_status": remote_status,
		"gateway_says_paid": remote_paid,
		"local_status": order.status,
		"changed": False,
		"discrepancy": None,
	}

	if remote_paid and order.status != "Paid":
		if not payment_id:
			outcome["discrepancy"] = _(
				"The gateway says this order is paid but gave no payment id, so it cannot "
				"be applied automatically."
			)
		else:
			payments.apply_successful_payment(order, payment_id, "Gateway Fetch")
			outcome["changed"] = True
			outcome["local_status"] = "Paid"
	elif order.status == "Paid" and not remote_paid:
		# Never reversed automatically. See the docstring.
		outcome["discrepancy"] = _(
			"We hold this order as paid but the gateway does not. Nothing has been "
			"changed. Check the settlement report before doing anything else."
		)

	audit.record(
		"Payment Status Refetched",
		f"Gateway reports {remote_status or 'unknown'} for {order.name}",
		reference_doctype="Payment Order",
		reference_name=order.name,
		amount=order.total_amount,
		detail=json.dumps(outcome, default=str, indent=1),
	)
	if outcome["discrepancy"]:
		frappe.log_error(
			title="a3_sola: payment status discrepancy",
			message=f"{order.name}: {outcome['discrepancy']}",
		)
	return outcome


def _payment_id_from(remote, client, order):
	"""A fetched order carries payments only on a second call; a link carries them inline."""
	from a3_sola.api.gateways.exceptions import GatewayError

	for payment in remote.get("payments") or []:
		if (payment.get("status") or "").lower() in GATEWAY_PAID:
			return payment.get("payment_id") or payment.get("id")
	if remote.get("payment_id"):
		return remote["payment_id"]
	if order.gateway_order_id:
		try:
			fetched = client.fetch_order_payments(order.gateway_order_id)
		except GatewayError:
			return None
		for payment in (fetched or {}).get("items") or []:
			if (payment.get("status") or "").lower() in GATEWAY_PAID:
				return payment.get("id")
	return None


@frappe.whitelist()
def mark_paid_manually(payment_order, reason, external_reference=None, received_on=None):
	"""Assert a payment the gateway cannot confirm - a NEFT transfer, a cheque, a cash deal.

	This is the most dangerous action in the module, so it is the most constrained: a
	higher role, a mandatory reason, a mandatory external reference, and a refusal to run
	at all if the gateway can still be asked. An operator who reaches for this while a
	gateway order is outstanding is told to fetch the status first, because nine times out
	of ten that resolves it correctly and this one does not.
	"""
	require_role(OVERRIDE_ROLES, _("Recording a payment by hand"))
	from a3_sola.api import payments

	reason = _reason(reason, _("recording this payment by hand"))
	external_reference = (external_reference or "").strip()
	if not external_reference:
		frappe.throw(
			_("Enter the bank reference, UTR or cheque number. A manual payment with no "
			  "external reference cannot be reconciled later.")
		)

	order = frappe.get_doc("Payment Order", payment_order)
	if order.status == "Paid":
		frappe.throw(_("{0} is already marked paid.").format(order.name))
	if order.gateway_order_id:
		frappe.throw(
			_("This order exists at the gateway. Fetch its status first - if the money "
			  "did arrive through the gateway, that will find it and record it properly.")
		)

	audit.record(
		"Manual Payment Override",
		f"{order.name} marked paid by hand for {order.currency} {flt(order.total_amount, 2)}",
		reference_doctype="Payment Order",
		reference_name=order.name,
		platform_subscription=order.platform_subscription,
		amount=order.total_amount,
		reason=reason,
		value_before=order.status,
		value_after="Paid",
		detail=(
			f"External reference: {external_reference}\n"
			f"Received on: {received_on or today()}\n"
			"No gateway confirmed this payment. It was asserted by an operator."
		),
	)
	# The audit entry is written first on purpose: if applying the payment fails halfway,
	# the attempt is still on record.
	payments.apply_successful_payment(
		order, f"manual:{external_reference}", "Manual Override"
	)
	if received_on:
		order.db_set("paid_on", get_datetime(received_on), update_modified=False)
	return {"status": "Paid", "order": order.name}


@frappe.whitelist()
def reissue_payment_link(payment_order, reason=None):
	"""Send the customer a fresh link when the old one expired or never arrived.

	The old link is not cancelled at the gateway - if the customer pays it, the webhook
	still lands on the same order and is deduplicated by payment id. Cancelling would
	create a window where a customer paying at that exact moment gets an error.
	"""
	_operator()
	from a3_sola.api.billing_engine import _issue_payment_link
	from a3_sola.api.gateways.exceptions import GatewayError

	order = frappe.get_doc("Payment Order", payment_order)
	if order.status == "Paid":
		frappe.throw(_("{0} is already paid. There is nothing to collect.").format(order.name))
	if not order.platform_subscription:
		frappe.throw(_("Only a subscription renewal can be re-linked from here."))

	subscription = frappe.get_doc("Platform Subscription", order.platform_subscription)
	previous = order.gateway_payment_link_url
	try:
		link = _issue_payment_link(subscription, order)
	except GatewayError as exception:
		frappe.throw(_("The gateway refused to create a link: {0}").format(str(exception)))

	audit.record(
		"Payment Link Reissued",
		f"New payment link issued for {order.name}",
		reference_doctype="Payment Order",
		reference_name=order.name,
		platform_subscription=order.platform_subscription,
		amount=order.total_amount,
		reason=reason,
		value_before=previous,
		value_after=link.get("short_url"),
		detail="The previous link was left live so a customer already paying it is not interrupted.",
	)
	return {"url": link.get("short_url"), "id": link.get("id")}


# -------------------------------------------------------------------- webhooks
@frappe.whitelist()
def reprocess_webhook(log_name, reason=None):
	"""Run a stored webhook through its handler again.

	Safe by construction - every handler is idempotent, which is what makes replaying one
	a reasonable first response to a processing failure rather than a gamble.
	"""
	_operator()
	from a3_sola.api import webhooks

	log = frappe.get_doc("Payment Webhook Log", log_name)
	if not log.signature_verified:
		frappe.throw(
			_("This event never passed signature verification, so its contents are not "
			  "trustworthy and it will not be processed.")
		)
	before = log.processing_status
	result = webhooks.reprocess(log_name)
	after = frappe.db.get_value("Payment Webhook Log", log_name, "processing_status")

	audit.record(
		"Webhook Reprocessed",
		f"{log.event_type or 'event'} {log.event_id} reprocessed",
		reference_doctype="Payment Webhook Log",
		reference_name=log_name,
		reason=reason,
		value_before=before,
		value_after=after,
	)
	return {"status": after, "result": result}


# -------------------------------------------------------------------- mandates
@frappe.whitelist()
def reregister_mandate(platform_subscription, reason=None):
	"""Ask the customer to authorise a new mandate.

	Used after a card expires or a bank rejects a token. The old mandate is cancelled
	first, and the subscription drops to assisted renewal in the meantime, so a debit is
	never attempted against a mandate the bank has already refused.
	"""
	_operator()
	from a3_sola.api import payments

	subscription = frappe.get_doc("Platform Subscription", platform_subscription)
	old_mandate = subscription.payment_mandate
	if old_mandate:
		mandate = frappe.get_doc("Payment Mandate", old_mandate)
		if mandate.docstatus == 1 and mandate.status not in ("Cancelled", "Rejected"):
			mandate.db_set(
				{
					"status": "Cancelled",
					"cancelled_on": today(),
					"cancellation_source": "Operations",
					"status_reason": (reason or "")[:500] or "Superseded by re-registration",
				},
				update_modified=False,
			)

	subscription.db_set(
		{
			"payment_mandate": None,
			"mandate_status": "Re-registration requested",
			"collection_route": "Assisted Renewal",
			"route_reason": _(
				"Automatic debit is paused until the customer authorises a new mandate."
			),
		},
		update_modified=False,
	)
	_notify_reregistration(subscription)

	audit.record(
		"Mandate Re-registered",
		f"Re-registration requested for {subscription.organisation_name}",
		reference_doctype="Platform Subscription",
		reference_name=subscription.name,
		platform_subscription=subscription.name,
		reason=reason,
		value_before=old_mandate or "(none)",
		value_after="(awaiting customer authorisation)",
		detail="Collection moved to assisted renewal until a new mandate is authorised.",
	)
	return {"subscription": subscription.name, "previous_mandate": old_mandate}


def _notify_reregistration(subscription):
	from a3_sola.api.settings import get_value

	if frappe.flags.in_test or frappe.flags.in_demo:
		return
	product = get_value("product_name") or "a3 sola"
	try:
		frappe.sendmail(
			recipients=[subscription.primary_contact_email],
			subject=_("Please re-authorise your {0} subscription payment").format(product),
			message=frappe.render_template(
				"a3_sola/templates/emails/mandate_reregistration.html",
				{
					"subscription": subscription,
					"product_name": product,
					"company_legal_name": get_value("company_legal_name") or "",
					"sales_email": get_value("sales_email"),
					"billing_url": frappe.utils.get_url("/billing"),
				},
			),
			reference_doctype=subscription.doctype,
			reference_name=subscription.name,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title="a3_sola: re-registration notice not sent",
			message=f"{subscription.name}\n\n{frappe.get_traceback()}",
		)


@frappe.whitelist()
def cancel_mandate_as_operator(platform_subscription, reason):
	"""Cancel on the customer's behalf - they rang up rather than clicking the button."""
	_operator()
	reason = _reason(reason, _("cancelling this mandate for the customer"))
	subscription = frappe.get_doc("Platform Subscription", platform_subscription)
	if not subscription.payment_mandate:
		frappe.throw(_("There is no active mandate on this subscription."))

	mandate = frappe.get_doc("Payment Mandate", subscription.payment_mandate)
	mandate.db_set(
		{
			"status": "Cancelled",
			"cancelled_on": today(),
			"cancellation_source": "Operations",
			"status_reason": reason[:500],
		},
		update_modified=False,
	)
	subscription.db_set(
		{
			"payment_mandate": None,
			"mandate_status": "Cancelled",
			"collection_route": "Assisted Renewal",
			"route_reason": _("The mandate was cancelled at the customer's request."),
		},
		update_modified=False,
	)
	audit.record(
		"Mandate Cancelled",
		f"Mandate {mandate.name} cancelled by operations",
		reference_doctype="Payment Mandate",
		reference_name=mandate.name,
		platform_subscription=subscription.name,
		reason=reason,
		value_before="Active",
		value_after="Cancelled",
	)
	return {"mandate": mandate.name, "status": "Cancelled"}


# -------------------------------------------------------------- reconciliation
@frappe.whitelist()
def run_reconciliation_for_range(from_date, to_date, gateway=None):
	"""Re-run matching across a date range, for when a settlement arrived out of order.

	Matching is pure: it looks at payments and settlement lines and pairs them. Running it
	again over a range costs nothing and can only improve the picture, which is why this
	is safe to hand to an operator rather than keeping it a developer command.
	"""
	_operator()
	from a3_sola.api import reconciliation

	filters = {
		"settlement_date": ["between", [from_date, to_date]],
		"docstatus": ["<", 2],
	}
	if gateway:
		filters["gateway"] = gateway

	names = frappe.get_all("Settlement Reconciliation", filters=filters, pluck="name")
	summary = {"reconciliations": len(names), "matched": 0, "unmatched": 0, "names": names}
	for name in names:
		doc = frappe.get_doc("Settlement Reconciliation", name)
		reconciliation.match(doc)
		summary["matched"] += cint(doc.matched_count)
		summary["unmatched"] += cint(doc.unmatched_count)

	audit.record(
		"Reconciliation Imported",
		f"Re-matched {len(names)} settlements from {from_date} to {to_date}",
		reference_doctype="Settlement Reconciliation",
		reference_name=names[0] if names else None,
		detail=json.dumps(summary, default=str, indent=1),
	)
	return summary


@frappe.whitelist()
def audit_trail(reference_doctype, reference_name):
	"""What the desk shows in the 'History' dialog on a payment record."""
	frappe.has_permission(reference_doctype, "read", doc=reference_name, throw=True)
	return audit.trail_for(reference_doctype, reference_name)
