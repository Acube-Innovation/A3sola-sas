# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The nightly lifecycle run: decide, for every tenant, whether they still have access.

Six passes, in order. Each subscription is processed inside its own try/except, so one bad
record cannot stop the run - a lifecycle engine that halts on the first exception is a
lifecycle engine that silently stops enforcing anything.

TWO THINGS IN HERE EXIST BECAUSE OF HOW THIS FAILS IN PRODUCTION

*The circuit breaker.* Before any suspension is applied, the run counts how many it would
perform. Over the configured limit it halts, performs NONE of them, and alerts. A gateway
outage or an off-by-one in date arithmetic must never lock out the customer base, and a
halted run somebody investigates in the morning is always cheaper than mass suspension.

*The heartbeat.* The single most likely way this phase fails is not a wrong decision - it
is the job quietly not running at all, for weeks, with nothing visibly broken. So every
run stamps the time and the streak, and a separate check alerts on their absence.
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	date_diff,
	flt,
	getdate,
	now_datetime,
	today,
)

from a3_sola.api.settings import get_value

BATCH_DEFAULT = 200

#: Nothing is evaluated for these - they are over.
SKIP_STATES = ("Draft", "Terminated")


def run_lifecycle(simulate=False):
	"""The daily job. Returns a summary dict; writes one to the Scheduled Job Log too.

	`simulate=True` computes and returns every decision without writing an event or
	touching anything - that is the pre-go-live simulation tool, and it is the same code
	path so what it reports is what the engine would actually do.
	"""
	from a3_sola.api.lifecycle import notify

	started = now_datetime()
	summary = {
		"evaluated": 0, "transitions": 0, "restored": 0, "suspended": 0,
		"warned": 0, "renewal_notices": 0, "trials_ended": 0, "cancelled": 0,
		"errors": 0, "halted": False, "dry_run": bool(cint(get_value("dry_run_mode", 1))),
		"simulated": bool(simulate), "decisions": [],
	}
	if cint(get_value("lifecycle_kill_switch", 0)) and not simulate:
		summary["halted"] = True
		summary["halt_reason"] = "kill switch"
		_finish(summary, started, simulate)
		return summary

	batch = cint(get_value("state_evaluation_batch_size", BATCH_DEFAULT)) or BATCH_DEFAULT

	# EVERY non-terminal subscription, read in batches. The batch size limits how much is
	# held at once; it must never limit which subscriptions are looked at. An engine that
	# evaluates the first two hundred and silently ignores the rest is precisely the "too
	# lax" failure this phase exists to prevent - nothing errors, and a tenant runs for
	# months past non-payment.
	planned = []
	offset = 0
	while True:
		names = frappe.get_all(
			"Platform Subscription",
			filters={"status": ["not in", SKIP_STATES], "docstatus": ["<", 2]},
			pluck="name",
			order_by="creation asc",
			limit_start=offset,
			limit_page_length=batch,
		)
		if not names:
			break
		offset += len(names)
		for name in names:
			try:
				doc = frappe.get_doc("Platform Subscription", name)
				summary["evaluated"] += 1
				planned.extend(_evaluate(doc, summary, simulate))
			except Exception:
				summary["errors"] += 1
				frappe.log_error(frappe.get_traceback(),
				                 f"a3_sola: lifecycle evaluate {name}")

	summary["decisions"] = [
		{k: v for k, v in p.items() if k != "doc"} for p in planned
	]
	if simulate:
		_finish(summary, started, simulate)
		return summary

	# CIRCUIT BREAKER - counted across the whole run, before a single one is applied.
	limit = cint(get_value("max_suspensions_per_run", 10))
	would_suspend = [p for p in planned if p["to_state"] == "Suspended"]
	if limit and len(would_suspend) > limit:
		summary["halted"] = True
		summary["halt_reason"] = (
			f"{len(would_suspend)} suspensions exceeds the limit of {limit}"
		)
		_halt(summary, would_suspend, limit)
		_finish(summary, started, simulate)
		return summary

	for plan in planned:
		try:
			_apply(plan, summary)
		except Exception:
			summary["errors"] += 1
			frappe.log_error(frappe.get_traceback(),
			                 f"a3_sola: lifecycle apply {plan['subscription']}")
		frappe.db.commit()

	_finish(summary, started, simulate)
	return summary


# ------------------------------------------------------------------ evaluation
def _evaluate(doc, summary, simulate):
	"""Everything this subscription needs, as a list of planned actions."""
	from a3_sola.api.lifecycle import policy as policy_api
	from a3_sola.api.lifecycle import state_machine

	state_machine.refresh_derived(doc)
	planned = []

	# --- pass 1: trial expiry ------------------------------------------------
	if doc.status == "Trialing" and doc.trial_end_date and getdate(doc.trial_end_date) <= getdate(today()):
		summary["trials_ended"] += 1
		paid = _has_settled(doc)
		planned.append(_plan(doc, "Active" if paid else "Pending Payment",
		                     _("Trial ended{0}.").format("" if paid else _(", no payment collected")),
		                     stage="TRIAL-END"))
		return planned

	# --- pass 2: renewal notices --------------------------------------------
	if doc.status in ("Active", "Trialing"):
		if _renewal_notice_due(doc):
			summary["renewal_notices"] += 1

	# --- pass 3: policy evaluation ------------------------------------------
	policy_name, stage, overdue = policy_api.stage_for(doc)
	# `overdue` is handed on rather than recomputed: working it out costs an unpaid-invoice
	# query, and this job runs it for every subscription on the instance every night.
	change_on, change_to = policy_api.next_change(doc, policy_name, overdue=overdue)
	if not simulate:
		doc.db_set({
			"policy": policy_name,
			"next_state_change_on": change_on,
			"next_state_change_to": change_to,
		}, update_modified=False)

	# --- pass 5: restoration, checked before anything restrictive ------------
	# Deliberately ahead of the transitions below: a subscription that has both cleared
	# its balance and crossed a suspension threshold overnight must be restored, not
	# suspended and then restored.
	#
	# `_has_settled` is called rather than inferred from `overdue`. They look like the same
	# question and are not: `is_overdue` answers True for anything in Past Due, Grace or
	# Suspended regardless of the balance, because that is what drives the policy stages.
	# `_has_settled` asks whether money is actually owed. Collapsing the two to save a
	# query stopped every suspended-but-paid tenant from being restored.
	if doc.status in ("Past Due", "Grace", "Suspended") and _has_settled(doc):
		summary["restored"] += 1
		return [_plan(doc, "Active", _("Outstanding balance cleared."),
		              policy=policy_name, stage="RESTORE", restore=True)]

	# --- pass 6: cancellation maturity ---------------------------------------
	if doc.status == "Cancelling" and doc.cancellation_effective_date:
		if getdate(doc.cancellation_effective_date) <= getdate(today()):
			summary["cancelled"] += 1
			return [_plan(doc, "Cancelled", _("The cancellation date has been reached."),
			              policy=policy_name, stage="CANCEL-MATURE")]

	if not stage:
		return planned

	if stage.stage_code != (doc.current_policy_stage or ""):
		target = stage.to_state or doc.status

		# A stage can call for a move the state machine forbids from where this
		# subscription actually is - a cancelled tenant reaching the policy's day-60
		# stage, for instance. Attempting it works: the transition refuses and names both
		# states, and the run carries on. But it writes an error every night for every
		# such subscription, and an error log full of expected failures is an error log
		# nobody reads. So the decision is still recorded, and the attempt is not made.
		reachable = target == doc.status or state_machine.legal(doc.status, target)
		planned.append(_plan(
			doc, target,
			_("Policy {0} stage {1} at day {2} overdue.{3}").format(
				policy_name, stage.stage_code, overdue if overdue is not None else 0,
				"" if reachable else _(
					" Not applied: {0} cannot move to {1}.").format(doc.status, target),
			),
			policy=policy_name, stage=stage.stage_code,
			effect=stage.access_effect, needs_approval=bool(stage.requires_approval),
			evaluated_only=(target in (None, "", doc.status)) or not reachable,
		))
	return planned


def _plan(doc, to_state, reason, policy=None, stage=None, effect=None,
          needs_approval=False, restore=False, evaluated_only=False):
	return {
		"doc": doc,
		"subscription": doc.name,
		"tenant": frappe.db.get_value("Tenant", {"platform_subscription": doc.name}, "name"),
		"from_state": doc.status,
		"to_state": to_state,
		"reason": reason,
		"policy": policy,
		"stage": stage,
		"effect": effect,
		"needs_approval": needs_approval,
		"restore": restore,
		"evaluated_only": evaluated_only,
		"amount_at_risk": flt(doc.recurring_amount),
	}


# ------------------------------------------------------------------ application
def _apply(plan, summary):
	from a3_sola.api.lifecycle import events, state_machine, suspension as suspension_api

	doc = plan["doc"]

	if plan["evaluated_only"]:
		events.record(
			subscription=doc.name, event_type="Policy Evaluated", reason=plan["reason"],
			triggered_by="Scheduler", from_state=plan["from_state"],
			to_state=plan["to_state"], policy=plan["policy"], policy_stage=plan["stage"],
			access_effect_applied=plan["effect"], amount_at_risk=plan["amount_at_risk"],
			was_dry_run=cint(get_value("dry_run_mode", 1)),
		)
		return

	if plan["to_state"] == "Suspended":
		blocked = _suspension_guards(plan, summary)
		if blocked:
			return
		if cint(get_value("require_manual_approval_for_suspension", 1)):
			suspension_api.request_approval(plan)
			summary["warned"] += 1
			return
		summary["suspended"] += 1

	if plan["restore"]:
		suspension_api.restore_if_suspended(plan)

	state_machine.transition(
		doc,
		plan["to_state"],
		plan["reason"],
		triggered_by="Scheduler",
		policy=plan["policy"],
		policy_stage=plan["stage"],
		access_effect=plan["effect"],
		amount_at_risk=plan["amount_at_risk"],
	)
	summary["transitions"] += 1


def _suspension_guards(plan, summary):
	"""Every reason not to switch somebody off. Returns a reason string, or None."""
	from a3_sola.api.lifecycle import events

	doc = plan["doc"]
	if not cint(get_value("enable_automatic_suspension", 0)):
		reason = _("Automatic suspension is switched off; the decision was recorded only.")
	elif cint(doc.lifetime_days_active or 0) < cint(get_value("min_days_active_before_suspension", 14)):
		reason = _("Tenant is {0} days old; the minimum tenure before suspension is {1}.").format(
			cint(doc.lifetime_days_active or 0),
			cint(get_value("min_days_active_before_suspension", 14)),
		)
	else:
		return None

	events.record(
		subscription=doc.name, event_type="Policy Evaluated",
		reason=f"{plan['reason']} {reason}", triggered_by="Scheduler",
		from_state=plan["from_state"], to_state=plan["to_state"],
		policy=plan["policy"], policy_stage=plan["stage"],
		amount_at_risk=plan["amount_at_risk"], was_dry_run=1,
	)
	return reason


def _halt(summary, would_suspend, limit):
	"""Perform none of them, say so once in the log, and alert a human."""
	from a3_sola.api.lifecycle import events, notify

	listing = "\n".join(
		f"  {p['subscription']} ({p['tenant'] or 'no tenant'}) - {p['reason']}"
		for p in would_suspend
	)
	message = (
		f"The lifecycle run would have suspended {len(would_suspend)} tenants, over the "
		f"limit of {limit}. NOTHING WAS SUSPENDED and the whole pass was abandoned.\n\n"
		f"This is the circuit breaker. It usually means a gateway outage or a date bug, "
		f"not {len(would_suspend)} customers deciding to stop paying on the same night.\n\n"
		f"{listing}\n"
	)
	notify.alert_internal("a3_sola: lifecycle run HALTED by the circuit breaker", message)
	first = would_suspend[0]
	events.record(
		subscription=first["subscription"], event_type="Policy Evaluated",
		reason=f"Circuit breaker halted the run: {len(would_suspend)} suspensions over a limit of {limit}.",
		reason_detail=listing, triggered_by="Scheduler", was_dry_run=1,
	)


# ------------------------------------------------------------------- helpers
def _has_settled(subscription):
	"""Nothing outstanding. The one question restoration turns on, so it is narrow."""
	if cint(subscription.get("consecutive_failures")):
		return False
	unpaid = frappe.get_all(
		"Subscription Invoice",
		filters={"platform_subscription": subscription.name,
		         "payment_status": ["in", ["Unpaid", "Partially Paid"]],
		         "docstatus": ["<", 2]},
		pluck="name",
	)
	return not unpaid


def _renewal_notice_due(subscription):
	"""Notices at each configured offset. Assisted Renewal customers get theirs earlier,
	because they have to act rather than just let a debit happen."""
	from a3_sola.api.lifecycle import notify

	if not subscription.next_billing_date:
		return False
	offsets = [
		cint(x) for x in str(get_value("notify_days_before_renewal", "7,3,1")).split(",")
		if str(x).strip().isdigit()
	]
	if subscription.collection_route == "Assisted Renewal":
		offsets = sorted({o for o in offsets} | {max(offsets or [7]) + 7})
	days_left = date_diff(getdate(subscription.next_billing_date), getdate(today()))
	if days_left not in offsets:
		return False
	if cint(get_value("dry_run_mode", 1)):
		return True
	notify.on_transition(subscription, subscription.status, subscription.status,
	                     _("Renewal due in {0} days.").format(days_left))
	return True


def _finish(summary, started, simulate):
	summary["seconds"] = round((now_datetime() - started).total_seconds(), 2)
	if not simulate:
		heartbeat(summary)
	frappe.logger("a3_sola").info({"event": "lifecycle_run", **{
		k: v for k, v in summary.items() if k != "decisions"
	}})
	return summary


# ------------------------------------------------------------------ heartbeat
def heartbeat(summary=None):
	"""Stamp that the engine ran, and how many days running it has.

	A job that stops is invisible: nothing errors, billing simply does not happen. The
	streak is what makes the absence detectable.
	"""
	last = get_value("lifecycle_heartbeat_on")
	streak = cint(get_value("lifecycle_heartbeat_streak_days", 0))
	if last and date_diff(today(), getdate(last)) <= 1:
		streak = streak + (1 if date_diff(today(), getdate(last)) == 1 else 0)
	else:
		streak = 1
	frappe.db.set_single_value("A3 Sola Settings", {
		"lifecycle_heartbeat_on": now_datetime(),
		"lifecycle_heartbeat_streak_days": streak,
	})
	return streak


def alert_on_missing_heartbeat():
	"""Daily. The check that catches the engine having quietly stopped."""
	from a3_sola.api.lifecycle import notify

	last = get_value("lifecycle_heartbeat_on")
	if not last:
		notify.alert_internal(
			"a3_sola: the lifecycle engine has never run",
			"No heartbeat has ever been recorded. Subscriptions are not being evaluated.",
		)
		return False
	stale = date_diff(today(), getdate(last))
	if stale >= 2:
		notify.alert_internal(
			"a3_sola: the lifecycle engine has stopped",
			f"The last lifecycle run was {stale} days ago, on {last}. Nothing is being "
			f"evaluated: no renewals chased, no restorations applied, no policy enforced. "
			f"Check the scheduler.",
		)
		return False
	return True


def simulate(days=0):
	"""The pre-go-live tool: every decision the engine would make, writing nothing."""
	return run_lifecycle(simulate=True)
