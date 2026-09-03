# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Resolving which policy governs a subscription, and which stage it has reached."""

import frappe
from frappe.utils import cint, date_diff, getdate, today

from a3_sola.api.settings import get_value

#: Distinguishes "not passed" from "passed as None", which is a real answer here.
_UNSET = object()


def resolve(subscription):
	"""The policy for this subscription: most specific active one wins.

	Plan and cycle beat plan alone, which beats the default. A client running one policy
	for annual customers and another for monthly gets that by creating two records, not by
	asking for a code change.
	"""
	plan = subscription.get("subscription_plan")
	cycle = subscription.get("billing_cycle")
	candidates = _active_policies()
	if not candidates:
		return None

	def score(row):
		if row.applicable_plan and row.applicable_plan != plan:
			return -1
		if row.applicable_cycle not in (None, "", "All") and row.applicable_cycle != cycle:
			return -1
		return (2 if row.applicable_plan else 0) + (
			1 if row.applicable_cycle not in (None, "", "All") else 0
		)

	ranked = sorted(
		((score(r), r) for r in candidates if score(r) >= 0),
		key=lambda pair: (pair[0], 1 if pair[1].is_default else 0),
		reverse=True,
	)
	if ranked:
		return ranked[0][1].name
	configured = get_value("default_subscription_policy")
	if configured and frappe.db.exists("Subscription Policy", configured):
		return configured
	fallback = frappe.db.get_value("Subscription Policy", {"is_default": 1, "is_active": 1}, "name")
	return fallback


def _active_policies():
	"""The active policies, read once per request rather than once per subscription.

	The nightly engine calls `resolve` for every subscription on the instance. Without
	this the policy table is read four hundred times to get four hundred identical
	answers - a third of that job's query count for a list that changes about never.

	Request-scoped rather than redis-cached on purpose: a policy edited in the desk takes
	effect on the next run, not after a cache expiry somebody has to remember.
	"""
	cached = getattr(frappe.local, "_a3s_active_policies", None)
	if cached is not None:
		return cached
	rows = frappe.get_all(
		"Subscription Policy",
		filters={"is_active": 1},
		fields=["name", "applicable_plan", "applicable_cycle", "is_default"],
	)
	frappe.local._a3s_active_policies = rows
	return rows


def is_overdue(subscription):
	"""Does this subscription actually owe money right now?

	Asked separately from "how many days", because the two get conflated and the result is
	the worst bug this file can have: a healthy customer matching a policy stage written
	for day 0 and being told their payment failed.
	"""
	if cint(subscription.get("consecutive_failures")):
		return True
	if subscription.get("status") in ("Past Due", "Grace", "Suspended"):
		return True
	return bool(frappe.get_all(
		"Subscription Invoice",
		filters={
			"platform_subscription": subscription.get("name"),
			"payment_status": ["in", ["Unpaid", "Partially Paid"]],
			"due_date": ["<=", today()],
			"docstatus": ["<", 2],
		},
		limit=1,
	))


def days_overdue(subscription):
	"""Calendar days since the money was due, or None when nothing is owed.

	None rather than zero, because zero is a real and different answer - "the payment
	failed today" - and a policy stage written for day 0 has to fire for that and not for
	a customer who owes nothing at all.

	Measured from `next_billing_date` because that is the date the customer agreed to and
	the date every notice quotes. Measuring from the last failure would restart the clock
	on every retry.
	"""
	if not is_overdue(subscription):
		return None
	due = subscription.get("next_billing_date")
	if not due:
		return 0
	return max(0, date_diff(today(), getdate(due)))


def stage_for(subscription, policy_name=None, dunning_exhausted=False):
	"""(policy name, stage row or None, days overdue) for a subscription right now."""
	policy_name = policy_name or resolve(subscription)
	if not policy_name:
		return None, None, None
	overdue = days_overdue(subscription)
	if overdue is None and not dunning_exhausted:
		# Nothing is owed. No day-driven stage applies, whatever its offset.
		return policy_name, None, None
	policy = frappe.get_cached_doc("Subscription Policy", policy_name)
	return policy_name, policy.stage_for(overdue or 0, dunning_exhausted), overdue


def next_change(subscription, policy_name=None, overdue=_UNSET):
	"""(date, to_state) for the next scheduled move, or (None, None).

	Computed rather than stored so it cannot go stale, and surfaced on the subscription so
	both the tenant and support can see what happens next without asking anybody.

	`overdue` is passed in by the engine, which has already worked it out. Recomputing it
	means a second unpaid-invoice query per subscription for an answer already in hand.
	"""
	policy_name = policy_name or resolve(subscription)
	if not policy_name or not subscription.get("next_billing_date"):
		return None, None
	policy = frappe.get_cached_doc("Subscription Policy", policy_name)
	if overdue is _UNSET:
		overdue = days_overdue(subscription)
	if overdue is None:
		# Not overdue: the next thing that happens is the renewal, not a policy stage.
		return getdate(subscription.next_billing_date), "Past Due"
	due = getdate(subscription.next_billing_date)
	upcoming = [
		row for row in sorted(policy.stages, key=lambda r: cint(r.sequence))
		if row.trigger_type in ("Days After Due Date", "Days After Failure")
		and cint(row.day_offset) > overdue
	]
	if not upcoming:
		return None, None
	row = upcoming[0]
	return frappe.utils.add_days(due, cint(row.day_offset)), row.to_state
