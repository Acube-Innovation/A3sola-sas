# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The daily recurring collection run.

Five passes, in this order, each idempotent and each safe to re-run:

1. **Pre-debit notification.** Regulatory, not a courtesy. The RBI e-mandate framework
   requires notifying the customer before every automatic debit.
2. **Auto-debit.** Only for subscriptions with an active mandate AND a notice that was
   actually sent in time.
3. **Assisted renewal.** A payment link, issued early, for anything that cannot be
   silently debited.
4. **Post-debit confirmation.** Also regulatory, after every successful collection.
5. **Failure handling.** Counters, Past Due, and a clean handoff to dunning.

**A debit whose notice was not sent in time is refused, loudly.** That refusal is the
whole point of pass 1 - debiting without notice is a compliance breach, and a run that
"catches up" by skipping the notice would be worse than a missed collection.

Each subscription is processed in its own try/except so one bad record cannot halt the
run, and the batch size is capped so a backlog degrades rather than times out.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, flt, get_datetime, getdate, now_datetime, today

from a3_sola.api import payments
from a3_sola.api.settings import get_int, get_value

BATCH_SIZE = 200
#: How far ahead an assisted-renewal link goes out. Annual gets longer, because an annual
#: renewal is a decision the customer may need to budget for.
LINK_LEAD_DAYS = {"Monthly": 7, "Annual": 21}


def run_daily_billing():
	"""The scheduled entry point. Registered through the platform registry."""
	summary = {
		"notified": 0, "debited": 0, "links_issued": 0,
		"confirmed": 0, "failed": 0, "blocked_no_notice": 0, "errors": 0,
	}
	for pass_name, handler in (
		("notify", pre_debit_notification_pass),
		("debit", auto_debit_pass),
		("assist", assisted_renewal_pass),
		("confirm", post_debit_confirmation_pass),
	):
		try:
			handler(summary)
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: billing pass {pass_name}")

	frappe.logger("a3_sola").info({"event": "daily_billing_run", **summary})
	return summary


# ------------------------------------------------------------------- pass one
def pre_debit_notification_pass(summary):
	"""Send the mandatory advance notice for every debit coming up."""
	notice_hours = get_int("pre_debit_notice_hours", 24) or 24
	horizon = add_to_date(now_datetime(), hours=notice_hours * 2)

	for name in _due_subscriptions("Auto Debit", getdate(horizon)):
		try:
			subscription = frappe.get_doc("Platform Subscription", name)
			cycle = _ensure_cycle(subscription)
			if cycle.notice_sent_on:
				continue
			_send_pre_debit_notice(subscription, cycle)
			summary["notified"] += 1
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: pre-debit notice {name}")


def _send_pre_debit_notice(subscription, cycle):
	"""Everything the framework requires the customer to be told, in one message."""
	context = {
		"subscription": subscription,
		"cycle": cycle,
		"amount": frappe.utils.fmt_money(cycle.amount, currency=subscription.currency),
		"debit_date": frappe.utils.formatdate(cycle.debit_date),
		"mandate": subscription.payment_mandate,
		"product_name": get_value("product_name") or "a3 sola",
		"company_legal_name": get_value("company_legal_name") or "",
		"sales_email": get_value("sales_email"),
	}
	if not (frappe.flags.in_test or frappe.flags.in_demo):
		try:
			frappe.sendmail(
				recipients=[subscription.primary_contact_email],
				subject=_("Upcoming payment of {0} on {1}").format(
					context["amount"], context["debit_date"]
				),
				message=frappe.render_template(
					"a3_sola/templates/emails/pre_debit_notice.html", context
				),
				reference_doctype=subscription.doctype,
				reference_name=subscription.name,
				now=False,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: notice {subscription.name}")
			return False

	# Recorded against the cycle, so it is auditable and so pass two can check it.
	cycle.db_set("notice_sent_on", now_datetime(), update_modified=False)
	cycle.db_set("outcome", "Notified", update_modified=False)
	return True


# ------------------------------------------------------------------- pass two
def auto_debit_pass(summary):
	"""Charge the mandate, but only where the notice was genuinely given in time."""
	notice_hours = get_int("pre_debit_notice_hours", 24) or 24

	for name in _due_subscriptions("Auto Debit", getdate(today())):
		try:
			subscription = frappe.get_doc("Platform Subscription", name)
			cycle = _ensure_cycle(subscription)
			if cycle.outcome == "Collected":
				continue

			blocked = _notice_blocker(cycle, notice_hours)
			if blocked:
				summary["blocked_no_notice"] += 1
				_alert_missing_notice(subscription, cycle, blocked)
				continue

			mandate = _active_mandate(subscription)
			if not mandate:
				summary["failed"] += 1
				_record_failure(subscription, cycle, _("No active mandate to debit."))
				continue
			if not mandate.covers(cycle.amount):
				summary["failed"] += 1
				_record_failure(
					subscription, cycle,
					_("The debit of {0} is above the {1} the customer authorised.").format(
						cycle.amount, mandate.registered_max_amount
					),
				)
				continue

			_charge_cycle(subscription, cycle, summary)
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: auto debit {name}")


def _notice_blocker(cycle, notice_hours):
	"""Return a reason string when this cycle must NOT be debited, else None."""
	if not cycle.notice_sent_on:
		return _("No pre-debit notice has been sent for this cycle.")
	elapsed = frappe.utils.time_diff_in_hours(now_datetime(), get_datetime(cycle.notice_sent_on))
	if elapsed < notice_hours:
		return _(
			"The pre-debit notice was sent {0} hours ago; {1} hours are required."
		).format(int(elapsed), notice_hours)
	return None


def _alert_missing_notice(subscription, cycle, reason):
	"""A hard block, and a loud one. This is a compliance guard, not a retry."""
	frappe.log_error(
		title="a3_sola: debit blocked, no notice",
		message=f"Debit blocked for {subscription.name}: {reason} Debiting without the required "
		"advance notice would breach the RBI e-mandate framework, so the collection has "
		"been skipped and will be retried once notice has been given.",
	)
	frappe.logger("a3_sola").warning(
		{"event": "debit_blocked_no_notice", "subscription": subscription.name}
	)


def _charge_cycle(subscription, cycle, summary):
	"""Create the renewal order and charge it. Cannot double-charge a period."""
	key = payments.idempotency_key(
		"Platform Subscription", subscription.name, "Renewal", str(cycle.period_start)
	)
	existing = frappe.db.get_value("Payment Order", {"idempotency_key": key}, "name")
	if existing:
		order = frappe.get_doc("Payment Order", existing)
		if order.status == "Paid":
			cycle.db_set("outcome", "Collected", update_modified=False)
			return order
	else:
		order = _renewal_order(subscription, cycle, key)

	cycle.db_set("payment_order", order.name, update_modified=False)

	from a3_sola.api.gateways.exceptions import GatewayError
	from a3_sola.api.gateways.razorpay_client import get_client

	try:
		client = get_client()
		gateway_order = client.create_order(
			amount_in_paise=cint(order.amount_in_paise),
			currency=order.currency,
			receipt=order.name,
			notes={"subscription": subscription.name, "cycle": str(cycle.period_start)},
		)
		order.db_set("gateway_order_id", gateway_order.get("id"), update_modified=False)
		# In the real flow the debit is raised against the mandate and settles by webhook.
		# The engine's job ends here: the webhook is what marks it Paid.
		order.db_set("status", "Pending", update_modified=False)
		cycle.db_set("outcome", "Pending", update_modified=False)
		summary["debited"] += 1
		return order
	except GatewayError as exc:
		summary["failed"] += 1
		_record_failure(subscription, cycle, str(exc))
		return None


def _renewal_order(subscription, cycle, key):
	from a3_sola.api import tax

	order = frappe.get_doc(
		{
			"doctype": "Payment Order",
			"reference_doctype": "Platform Subscription",
			"reference_name": subscription.name,
			"platform_subscription": subscription.name,
			"subscription_signup": subscription.subscription_signup,
			"customer_name": subscription.organisation_name,
			"customer_email": subscription.primary_contact_email,
			"customer_phone": subscription.primary_contact_phone,
			"order_type": "Renewal",
			"billing_cycle": subscription.billing_cycle,
			"description": _("{0} renewal, {1} to {2}").format(
				subscription.plan_code, cycle.period_start, cycle.period_end
			),
			"period_start": cycle.period_start,
			"period_end": cycle.period_end,
			"base_amount": subscription.base_amount,
			"additional_user_amount": subscription.additional_user_amount,
			"implementation_fee": 0,
			"subtotal": subscription.subtotal,
			"tax_amount": subscription.tax_amount,
			"total_amount": subscription.recurring_amount,
			"currency": subscription.currency,
			"place_of_supply": subscription.place_of_supply,
			"customer_gstin": subscription.gstin,
			"customer_state_code": subscription.state_code,
			"collection_mode": "Auto Debit",
			"collection_reason": subscription.route_reason,
			"idempotency_key": key,
		}
	)
	order.flags.ignore_permissions = True
	order.insert(ignore_permissions=True)
	return order


# ----------------------------------------------------------------- pass three
def assisted_renewal_pass(summary):
	"""Issue a payment link early, and explain why authentication is needed this time."""
	for name in _due_subscriptions("Assisted Renewal", None):
		try:
			subscription = frappe.get_doc("Platform Subscription", name)
			lead = LINK_LEAD_DAYS.get(subscription.billing_cycle, 7)
			if getdate(subscription.next_billing_date) > add_days(getdate(today()), lead):
				continue

			cycle = _ensure_cycle(subscription)
			if cycle.outcome in ("Collected", "Notified") and cycle.payment_order:
				continue

			key = payments.idempotency_key(
				"Platform Subscription", subscription.name, "Renewal", str(cycle.period_start)
			)
			existing = frappe.db.get_value("Payment Order", {"idempotency_key": key}, "name")
			order = (
				frappe.get_doc("Payment Order", existing)
				if existing
				else _renewal_order(subscription, cycle, key)
			)
			if order.gateway_payment_link_id:
				continue
			order.db_set("collection_mode", "Payment Link", update_modified=False)
			_issue_payment_link(subscription, order)
			cycle.db_set("payment_order", order.name, update_modified=False)
			cycle.db_set("outcome", "Notified", update_modified=False)
			summary["links_issued"] += 1
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: assisted renewal {name}")


def _issue_payment_link(subscription, order):
	from a3_sola.api.gateways.razorpay_client import get_client

	client = get_client()
	link = client.create_payment_link(
		amount_in_paise=cint(order.amount_in_paise),
		currency=order.currency,
		description=order.description,
		customer={
			"name": subscription.organisation_name,
			"email": subscription.primary_contact_email,
			"contact": subscription.primary_contact_phone,
		},
		reference_id=order.name,
		expire_by=None,
		notes={"subscription": subscription.name},
	)
	order.db_set(
		{
			"gateway_payment_link_id": link.get("id"),
			"gateway_payment_link_url": link.get("short_url"),
			"status": "Pending",
		},
		update_modified=False,
	)
	return link


# ------------------------------------------------------------------ pass four
def post_debit_confirmation_pass(summary):
	"""Confirm every successful collection. Also a framework requirement."""
	if not get_value("send_post_debit_confirmation"):
		return
	rows = frappe.get_all(
		"Subscription Billing Cycle",
		filters={"outcome": "Collected", "confirmation_sent_on": ["is", "not set"]},
		fields=["name", "parent", "amount", "period_start", "period_end", "payment_order"],
		limit_page_length=BATCH_SIZE,
	)
	for row in rows:
		try:
			subscription = frappe.get_doc("Platform Subscription", row.parent)
			if not (frappe.flags.in_test or frappe.flags.in_demo):
				frappe.sendmail(
					recipients=[subscription.primary_contact_email],
					subject=_("Payment received - {0}").format(
						frappe.utils.fmt_money(row.amount, currency=subscription.currency)
					),
					message=frappe.render_template(
						"a3_sola/templates/emails/post_debit_confirmation.html",
						{
							"subscription": subscription, "cycle": row,
							"amount": frappe.utils.fmt_money(
								row.amount, currency=subscription.currency
							),
							"product_name": get_value("product_name") or "a3 sola",
							"company_legal_name": get_value("company_legal_name") or "",
							"sales_email": get_value("sales_email"),
						},
					),
					reference_doctype=subscription.doctype,
					reference_name=subscription.name,
					now=False,
				)
			frappe.db.set_value(
				"Subscription Billing Cycle", row.name, "confirmation_sent_on",
				now_datetime(), update_modified=False,
			)
			summary["confirmed"] += 1
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: confirmation {row.name}")


# ------------------------------------------------------------------- failures
def _record_failure(subscription, cycle, reason):
	"""Counters, Past Due, and a clean handoff to dunning in P5-A3S-003."""
	cycle.db_set({"outcome": "Failed"}, update_modified=False)
	subscription.db_set(
		{
			"failed_payments": cint(subscription.failed_payments) + 1,
			"consecutive_failures": cint(subscription.consecutive_failures) + 1,
			"status": "Past Due",
			"status_reason": reason,
		},
		update_modified=False,
	)
	frappe.logger("a3_sola").warning(
		{"event": "collection_failed", "subscription": subscription.name, "reason": reason}
	)


def record_success(subscription, order):
	"""Called when a renewal settles. Rolls the period and hands to Phase 7."""
	from a3_sola.platform.doctype.platform_subscription.platform_subscription import (
		on_billing_cycle_completed,
		safely,
	)

	cycle = subscription.cycle_for(order.period_start)
	if cycle:
		cycle.db_set("outcome", "Collected", update_modified=False)
	subscription.db_set(
		{
			"successful_payments": cint(subscription.successful_payments) + 1,
			"consecutive_failures": 0,
			"last_successful_billing_date": today(),
			"lifetime_value": flt(subscription.lifetime_value) + flt(order.total_amount),
		},
		update_modified=False,
	)
	# Through set_status rather than the db_set above, so a first activation reaches the
	# lifecycle handoff instead of being written silently.
	subscription.set_status("Active", reason=_("Payment collected for the current period."))
	subscription.reload()
	subscription.advance_period()
	safely(on_billing_cycle_completed, subscription, "on_billing_cycle_completed")
	return subscription


# --------------------------------------------------------------------- helpers
def _due_subscriptions(route, on_or_before):
	filters = {
		"collection_route": route,
		"docstatus": 1,
		"status": ["in", ["Active", "Past Due"]],
	}
	if on_or_before:
		filters["next_billing_date"] = ["<=", on_or_before]
	return frappe.get_all(
		"Platform Subscription", filters=filters, pluck="name", limit_page_length=BATCH_SIZE
	)


def _ensure_cycle(subscription):
	"""The billing cycle row for the current period, created once."""
	existing = subscription.cycle_for(subscription.current_period_start)
	if existing:
		return existing
	subscription.append(
		"billing_cycles",
		{
			"period_start": subscription.current_period_start,
			"period_end": subscription.current_period_end,
			"debit_date": subscription.next_debit_date or subscription.next_billing_date,
			"amount": subscription.recurring_amount,
			"outcome": "Pending",
		},
	)
	subscription.flags.ignore_validate_update_after_submit = True
	subscription.save(ignore_permissions=True)
	subscription.reload()
	return subscription.cycle_for(subscription.current_period_start)


def _active_mandate(subscription):
	if not subscription.payment_mandate:
		return None
	mandate = frappe.get_doc("Payment Mandate", subscription.payment_mandate)
	return mandate if mandate.status == "Active" else None
