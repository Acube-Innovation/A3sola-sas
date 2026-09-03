# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The six extension points Phases 5 and 6 left for this one, implemented here.

Phases 5 and 6 deliberately stopped at the edge of policy. Collection knows a payment
failed; it does not get to decide that a customer loses access. Provisioning knows how to
build a tenant; it does not get to decide when to switch one off. Those decisions live in
this package, and these functions are where the earlier phases hand over.

Each keeps the contract its docstring promised, which is why the original docstrings are
quoted rather than replaced.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime, today

from a3_sola.api.settings import get_value


# ------------------------------------------------------- Phase 5: activation
def on_subscription_activated(subscription):
	"""Start the lifecycle clock.

	Contract from Phase 5: called once, when a subscription first becomes Active. Trial
	end, first renewal, entitlement grants.
	"""
	from a3_sola.api.lifecycle import events, policy as policy_api, state_machine

	trial_days = cint(_plan_value(subscription, "trial_days"))
	policy_name = policy_api.resolve(subscription)
	values = {"policy": policy_name, "state_since": now_datetime(), "days_in_state": 0}

	if trial_days and not subscription.get("trial_end_date"):
		# A trial is fully open and charges nothing. It is not a lesser Active.
		values["trial_end_date"] = add_days(today(), trial_days)
		subscription.db_set(values, update_modified=False)
		subscription.reload()
		state_machine.transition(
			subscription, "Trialing",
			_("Trial started: {0} days.").format(trial_days),
			triggered_by="API", policy=policy_name,
		)
		return "Trialing"

	subscription.db_set(values, update_modified=False)
	events.record(
		subscription=subscription, event_type="Activated",
		reason=_("Subscription activated."), triggered_by="API",
		to_state="Active", policy=policy_name, access_effect_applied="None",
	)
	state_machine.refresh_derived(subscription)
	return "Active"


# ---------------------------------------------------- Phase 5: cycle collected
def on_billing_cycle_completed(subscription):
	"""Advance the period and, if the balance is clear, bring the customer back.

	Contract from Phase 5: renewal policy after a successfully collected cycle. It does
	not collect money - that already happened.
	"""
	from a3_sola.api.lifecycle import engine, events, state_machine

	events.record(
		subscription=subscription, event_type="Renewed",
		reason=_("Billing cycle collected for the period ending {0}.").format(
			subscription.get("current_period_end")),
		triggered_by="Webhook", amount_at_risk=0,
	)
	subscription.db_set({"consecutive_failures": 0}, update_modified=False)
	subscription.reload()

	if subscription.status in ("Past Due", "Grace", "Suspended") and engine._has_settled(subscription):
		# Restoration is the fastest path in the system: it happens here, on the webhook,
		# not on the next nightly run.
		from a3_sola.api.lifecycle import suspension as suspension_api

		tenant = frappe.db.get_value("Tenant", {"platform_subscription": subscription.name}, "name")
		if tenant:
			suspension_api.restore(tenant, trigger="Payment Received",
			                       reason=_("Payment received; balance cleared."))
		else:
			state_machine.transition(
				subscription, "Active", _("Payment received; balance cleared."),
				triggered_by="Webhook",
			)
		return "Active"

	# A scheduled downgrade takes effect at the boundary, and this is the boundary.
	_apply_scheduled_changes(subscription)
	return subscription.status


# --------------------------------------------------- Phase 5: collection failed
def on_payment_failed_final(subscription):
	"""Enter Past Due. Access is untouched - that is the product decision, not an
	oversight.

	Contract from Phase 5: collection failed and dunning has run out of steps. Phase 5
	stops at Past Due; what happens after is policy.
	"""
	from a3_sola.api.lifecycle import policy as policy_api, state_machine

	if subscription.status in ("Past Due", "Grace", "Suspended", "Cancelled", "Terminated"):
		return subscription.status
	policy_name = policy_api.resolve(subscription)
	state_machine.transition(
		subscription, "Past Due",
		_("Collection failed after {0} attempt(s).").format(
			cint(subscription.get("consecutive_failures")) or 1),
		triggered_by="Webhook", policy=policy_name,
		amount_at_risk=flt(subscription.get("recurring_amount")),
	)
	return "Past Due"


# --------------------------------------------------- Phase 5: dunning exhausted
def on_dunning_exhausted(subscription):
	"""Hand the customer to the policy, subject to every guard.

	Contract from Phase 5: dunning has run every step and the subscription is still
	unpaid. Phase 5 refuses to suspend on its own, because cutting a customer off is a
	policy decision rather than a billing one.

	This does NOT suspend anybody directly. It moves the subscription to the stage the
	policy says it has reached, and the nightly engine - with its approval requirement,
	its minimum tenure and its circuit breaker - decides what happens from there.
	"""
	from a3_sola.api.lifecycle import events, policy as policy_api, state_machine

	policy_name, stage, overdue = policy_api.stage_for(
		subscription, dunning_exhausted=True
	)
	if not stage:
		events.record(
			subscription=subscription, event_type="Policy Evaluated",
			reason=_("Dunning is exhausted and no policy stage applies at day {0}. This "
			         "needs a person.").format(overdue if overdue is not None else 0),
			triggered_by="Scheduler", policy=policy_name, was_dry_run=1,
			amount_at_risk=flt(subscription.get("recurring_amount")),
		)
		return None

	target = stage.to_state or "Grace"
	if target == "Suspended":
		# Never straight from here. The engine owns suspension, with its guards.
		events.record(
			subscription=subscription, event_type="Policy Evaluated",
			reason=_("Dunning exhausted; policy stage {0} calls for suspension. Left to "
			         "the nightly engine and its guards.").format(stage.stage_code),
			triggered_by="Scheduler", policy=policy_name, policy_stage=stage.stage_code,
			amount_at_risk=flt(subscription.get("recurring_amount")), was_dry_run=1,
		)
		return None

	state_machine.transition(
		subscription, target,
		_("Dunning exhausted at day {0}; policy stage {1}.").format(
			overdue if overdue is not None else 0, stage.stage_code),
		triggered_by="Scheduler", policy=policy_name, policy_stage=stage.stage_code,
		access_effect=stage.access_effect,
		amount_at_risk=flt(subscription.get("recurring_amount")),
	)
	return target


# ------------------------------------------------------------- Phase 6: access
def set_tenant_access_state(tenant, state, reason):
	"""Phase 6's one funnel for access changes. Implemented in the access controller."""
	from a3_sola.api.lifecycle import access

	return access.set_tenant_access_state(tenant, state, reason)


# -------------------------------------------------------------- shared helpers
def _plan_value(subscription, field):
	plan = subscription.get("subscription_plan")
	if not plan:
		return None
	return frappe.db.get_value("Subscription Plan", plan, field)


def _apply_scheduled_changes(subscription):
	"""Downgrades and seat removals wait for the period boundary. This is it."""
	from a3_sola.api.lifecycle import plan_change

	pending = frappe.get_all(
		"Plan Change Request",
		filters={"platform_subscription": subscription.name, "status": "Scheduled",
		         "docstatus": 1},
		pluck="name",
	)
	for name in pending:
		try:
			plan_change.apply_plan_change(name)
		except Exception:
			frappe.log_error(frappe.get_traceback(),
			                 f"a3_sola: scheduled plan change {name}")
	return pending
