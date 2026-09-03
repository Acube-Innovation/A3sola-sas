# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Chasing a failed collection.

The schedule is a master, not code: a Dunning Policy with dated steps, so the client can
change when they nag without a deploy.

The important distinction here is between a **transient** failure and a **permanent** one.
Insufficient funds or a bank timeout is worth retrying - the money may be there tomorrow.
An expired card or a revoked mandate is not: retrying it just burns attempts and irritates
the customer, and what they actually need is a link to re-register. The mapping from
gateway code to class lives in the policy, so a new code the gateway invents is a data
change rather than a deploy.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from a3_sola.api.settings import get_value

#: A sensible default when the policy has no explicit mapping. Unknown is treated as
#: transient once and then not retried - optimistic, but only briefly.
DEFAULT_CLASSES = {
	"BAD_REQUEST_ERROR": "Transient",
	"GATEWAY_ERROR": "Transient",
	"SERVER_ERROR": "Transient",
	"insufficient_funds": "Transient",
	"payment_timed_out": "Transient",
	"issuer_down": "Transient",
	"card_expired": "Permanent",
	"card_declined_permanently": "Permanent",
	"mandate_revoked": "Permanent",
	"account_closed": "Permanent",
	"token_rejected": "Permanent",
}

DEFAULT_POLICY = {
	"policy_name": "Standard Dunning",
	"applies_to_cycle": "Any",
	"is_default": 1,
	"steps": [
		(0, "Email Reminder", "Payment did not go through", 0),
		(1, "Auto Retry", None, 0),
		(3, "Auto Retry", None, 0),
		(3, "Payment Link Issued", "Pay by link", 0),
		(7, "Email Reminder", "Second reminder", 0),
		(10, "Final Notice", "Final notice before suspension", 1),
	],
}


def seed_default_policy():
	"""Idempotent. Never overwrites a policy the client has tuned."""
	if frappe.db.exists("Dunning Policy", DEFAULT_POLICY["policy_name"]):
		return DEFAULT_POLICY["policy_name"]
	doc = frappe.get_doc(
		{
			"doctype": "Dunning Policy",
			"policy_name": DEFAULT_POLICY["policy_name"],
			"applies_to_cycle": DEFAULT_POLICY["applies_to_cycle"],
			"is_default": 1,
			"is_active": 1,
			"steps": [
				{
					"day_offset": offset,
					"action_type": action,
					"template": template,
					"is_final": is_final,
				}
				for offset, action, template, is_final in DEFAULT_POLICY["steps"]
			],
			"error_classes": [
				{
					"error_code": code,
					"error_class": klass,
					"requires_new_mandate": 1 if klass == "Permanent" else 0,
					"customer_message": (
						_("Your bank could not complete the payment. We will try again.")
						if klass == "Transient"
						else _("Your saved payment method is no longer usable and needs "
						       "to be set up again.")
					),
				}
				for code, klass in DEFAULT_CLASSES.items()
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def policy_for(subscription):
	"""The most specific active policy for this subscription's cycle."""
	exact = frappe.db.get_value(
		"Dunning Policy",
		{"is_active": 1, "applies_to_cycle": subscription.billing_cycle},
		"name",
	)
	if exact:
		return frappe.get_cached_doc("Dunning Policy", exact)
	default = frappe.db.get_value("Dunning Policy", {"is_active": 1, "is_default": 1}, "name")
	return frappe.get_cached_doc("Dunning Policy", default) if default else None


def classify_error(error_code, policy=None):
	"""Transient, Permanent or Unknown - and whether the mandate must be re-registered."""
	code = (error_code or "").strip()
	if policy:
		row = next(
			(r for r in policy.error_classes if (r.error_code or "").strip() == code), None
		)
		if row:
			return row.error_class, bool(row.requires_new_mandate), row.customer_message
	klass = DEFAULT_CLASSES.get(code, "Unknown")
	return klass, klass == "Permanent", None


def run_dunning():
	"""Daily: advance every past-due subscription through its policy."""
	summary = {"processed": 0, "retried": 0, "notified": 0, "exhausted": 0, "errors": 0}

	for name in frappe.get_all(
		"Platform Subscription",
		filters={"status": "Past Due", "docstatus": 1},
		pluck="name",
		limit_page_length=200,
	):
		try:
			_advance_one(frappe.get_doc("Platform Subscription", name), summary)
			summary["processed"] += 1
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: dunning {name}")

	frappe.logger("a3_sola").info({"event": "dunning_run", **summary})
	return summary


def _advance_one(subscription, summary):
	policy = policy_for(subscription)
	if not policy:
		return

	failed_on = _failure_date(subscription)
	if not failed_on:
		return
	days_since = frappe.utils.date_diff(today(), failed_on)

	error_code = _last_error_code(subscription)
	error_class, needs_new_mandate, message = classify_error(error_code, policy)

	for index, step in enumerate(policy.steps, start=1):
		if cint(step.day_offset) != days_since:
			continue
		if _already_attempted(subscription, index):
			continue

		# A permanent failure is not worth retrying. What the customer needs is a way to
		# fix the instrument, not a third decline on the same dead card.
		if step.action_type == "Auto Retry" and error_class == "Permanent":
			_record_attempt(
				subscription, index, "Email Reminder", outcome="Contacted",
				error_code=error_code,
				notes=_("Retry skipped: {0} is a permanent failure. Asked the customer to "
				        "re-register instead.").format(error_code or _("the bank's response")),
			)
			_notify(subscription, message or _(
				"Your saved payment method needs to be set up again."
			), needs_new_mandate=True)
			summary["notified"] += 1
			continue

		if step.action_type == "Auto Retry":
			_retry_collection(subscription, index, summary)
		elif step.action_type == "Payment Link Issued":
			_issue_link(subscription, index, summary)
		else:
			_record_attempt(subscription, index, step.action_type, outcome="Contacted")
			_notify(subscription, message, needs_new_mandate=needs_new_mandate)
			summary["notified"] += 1

		if step.is_final:
			_exhausted(subscription, summary)


def _failure_date(subscription):
	for row in reversed(subscription.billing_cycles or []):
		if row.outcome == "Failed":
			return getdate(row.debit_date or row.period_start)
	return None


def _last_error_code(subscription):
	order = frappe.db.get_value(
		"Payment Order",
		{"platform_subscription": subscription.name, "status": "Failed"},
		"last_error_code",
		order_by="creation desc",
	)
	return order


def _already_attempted(subscription, step_number):
	return any(
		cint(row.attempt_number) == step_number for row in subscription.dunning_attempts or []
	)


def _record_attempt(subscription, number, action, outcome=None, payment_order=None,
                    error_code=None, notes=None):
	subscription.append(
		"dunning_attempts",
		{
			"attempt_number": number,
			"attempt_date": now_datetime(),
			"attempt_type": action,
			"payment_order": payment_order,
			"outcome": outcome,
			"error_code": error_code,
			"notes": notes,
		},
	)
	subscription.flags.ignore_validate_update_after_submit = True
	subscription.save(ignore_permissions=True)


def _retry_collection(subscription, step_number, summary):
	from a3_sola.api import billing_engine

	cycle = billing_engine._ensure_cycle(subscription)
	order = billing_engine._charge_cycle(subscription, cycle, summary)
	_record_attempt(
		subscription, step_number, "Auto Retry",
		outcome="Succeeded" if order else "Failed",
		payment_order=order.name if order else None,
	)
	summary["retried"] += 1


def _issue_link(subscription, step_number, summary):
	from a3_sola.api import billing_engine

	cycle = billing_engine._ensure_cycle(subscription)
	key = None
	try:
		from a3_sola.api import payments

		key = payments.idempotency_key(
			"Platform Subscription", subscription.name, "Renewal", str(cycle.period_start)
		)
		existing = frappe.db.get_value("Payment Order", {"idempotency_key": key}, "name")
		order = (
			frappe.get_doc("Payment Order", existing)
			if existing
			else billing_engine._renewal_order(subscription, cycle, key)
		)
		if not order.gateway_payment_link_id:
			billing_engine._issue_payment_link(subscription, order)
		_record_attempt(
			subscription, step_number, "Payment Link Issued",
			outcome="Contacted", payment_order=order.name,
		)
		summary["notified"] += 1
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: dunning link {subscription.name}")


def _notify(subscription, message, needs_new_mandate=False):
	if frappe.flags.in_test or frappe.flags.in_demo:
		return
	try:
		frappe.sendmail(
			recipients=[subscription.primary_contact_email],
			subject=_("Your {0} payment needs attention").format(
				get_value("product_name") or "a3 sola"
			),
			message=frappe.render_template(
				"a3_sola/templates/emails/dunning_reminder.html",
				{
					"subscription": subscription,
					"message": message,
					"needs_new_mandate": needs_new_mandate,
					"product_name": get_value("product_name") or "a3 sola",
					"company_legal_name": get_value("company_legal_name") or "",
					"sales_email": get_value("sales_email"),
				},
			),
			reference_doctype=subscription.doctype,
			reference_name=subscription.name,
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: dunning notice {subscription.name}")


def _exhausted(subscription, summary):
	from a3_sola.platform.doctype.platform_subscription.platform_subscription import (
		on_payment_failed_final,
		safely,
	)

	summary["exhausted"] += 1
	# Two handoffs from one moment. Dunning exhaustion is a collection event; the final
	# payment failure is a subscription event. Phase 7 may want to act on one and not the
	# other, so both are offered rather than one standing in for both.
	safely(on_payment_failed_final, subscription, "on_payment_failed_final")
	try:
		on_dunning_exhausted(subscription)
	except NotImplementedError:
		frappe.logger("a3_sola").info(
			{"event": "dunning_exhausted_deferred", "subscription": subscription.name}
		)
		frappe.log_error(
			title="a3_sola: dunning exhausted",
			message=(
				f"Subscription {subscription.name} has run out of dunning steps and is "
				"still unpaid. Phase 7 owns suspension; until then this needs a person."
			),
		)


def on_dunning_exhausted(subscription):
	"""Phase 7 implements this. See a3_sola/api/lifecycle/handlers.py.

	Phase 5 deliberately stops here rather than suspending on its own: cutting a customer
	off is a policy decision, not a billing one. Phase 7 moves the subscription to the
	stage its policy says it has reached, and the nightly engine - with its approval
	requirement, its minimum tenure and its circuit breaker - decides the rest.
	"""
	from a3_sola.api.lifecycle.handlers import on_dunning_exhausted as implementation

	return implementation(subscription)
