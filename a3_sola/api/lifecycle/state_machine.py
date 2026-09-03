# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The subscription state machine: which moves are legal, and how one is made.

The table below is the whole contract. If a move is not in it, it does not happen - the
transition raises and names both states rather than quietly doing something reasonable.
That matters most for the move nobody should ever make directly: Active straight to
Suspended, skipping the policy stages that warn the customer first.

The other half of this module is `transition()`, which is the only function in the app
allowed to change a subscription's state. It writes the event BEFORE applying any effect,
so a crash between the two leaves a record of the intent rather than an unexplained
change.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, today, date_diff, getdate

from a3_sola.api.settings import get_value

#: Every state a subscription can be in. Access is a separate axis - see ACCESS_BY_STATE.
STATES = (
	"Draft",
	"Pending Payment",
	"Trialing",
	"Active",
	"Past Due",
	"Grace",
	"Suspended",
	"Cancelling",
	"Cancelled",
	"Terminated",
)

#: States nothing moves out of automatically.
TERMINAL = ("Terminated",)

#: The access a state implies unless a policy stage says otherwise.
#:
#: Past Due deliberately leaves access Full. A failed payment is usually a bank problem,
#: not a refusal to pay, and restricting a customer's work over one is how you lose the
#: account. Restriction begins at Grace, and only as a banner.
ACCESS_BY_STATE = {
	"Draft": "None",
	"Pending Payment": "None",
	"Trialing": "None",
	"Active": "None",
	"Past Due": "None",
	"Grace": "Banner Only",
	"Suspended": "Blocked",
	"Cancelling": "None",
	"Cancelled": "Blocked",
	"Terminated": "Blocked",
}

#: `access_state` is the field on the subscription; "None" as an effect means Full access.
EFFECT_TO_ACCESS_STATE = {
	"None": "Full",
	"Banner Only": "Banner",
	"Read Only": "Read Only",
	"Blocked": "Blocked",
}

TRIGGERS = ("Scheduler", "Webhook", "Tenant Self Service", "Internal User", "API")


class Transition:
	"""One legal move, and what it takes to make it."""

	__slots__ = ("to_state", "triggers", "needs_approval", "event_type", "note")

	def __init__(self, to_state, triggers, event_type, needs_approval=False, note=""):
		self.to_state = to_state
		self.triggers = triggers
		self.needs_approval = needs_approval
		self.event_type = event_type
		self.note = note


ANY = TRIGGERS
AUTOMATED = ("Scheduler", "Webhook")
HUMAN = ("Internal User", "Tenant Self Service", "API")

#: from_state -> {to_state: Transition}. The single source of truth for legality.
TABLE = {
	"Draft": {
		"Pending Payment": Transition("Pending Payment", ANY, "Provisioned"),
		"Trialing": Transition("Trialing", ANY, "Trial Started"),
		"Active": Transition("Active", ANY, "Activated"),
		"Cancelled": Transition("Cancelled", HUMAN, "Cancelled"),
	},
	"Pending Payment": {
		"Active": Transition("Active", ANY, "Activated"),
		"Trialing": Transition("Trialing", ANY, "Trial Started"),
		"Past Due": Transition("Past Due", ANY, "Entered Past Due"),
		"Cancelled": Transition("Cancelled", ANY, "Cancelled"),
	},
	"Trialing": {
		"Active": Transition("Active", ANY, "Activated"),
		"Pending Payment": Transition("Pending Payment", ANY, "Trial Ended"),
		# A trial that never had a payment method is cancelled, never suspended. There is
		# nothing to suspend them over: they never owed anything.
		"Cancelled": Transition("Cancelled", ANY, "Cancelled"),
	},
	"Active": {
		"Past Due": Transition("Past Due", ANY, "Entered Past Due"),
		"Cancelling": Transition("Cancelling", HUMAN, "Cancellation Requested"),
		# Deliberately absent: Active -> Suspended. A customer reaches Suspended through
		# Past Due and Grace, having been warned at each, or not at all.
		"Cancelled": Transition("Cancelled", HUMAN, "Cancelled",
		                        note="Immediate cancellation - internal approval only."),
	},
	"Past Due": {
		"Active": Transition("Active", ANY, "Restored"),
		"Grace": Transition("Grace", ANY, "Entered Grace"),
		"Cancelling": Transition("Cancelling", HUMAN, "Cancellation Requested"),
		"Cancelled": Transition("Cancelled", HUMAN, "Cancelled"),
	},
	"Grace": {
		"Active": Transition("Active", ANY, "Restored"),
		"Past Due": Transition("Past Due", ANY, "Entered Past Due"),
		"Suspended": Transition("Suspended", ANY, "Suspended", needs_approval=True),
		"Cancelling": Transition("Cancelling", HUMAN, "Cancellation Requested"),
		"Cancelled": Transition("Cancelled", HUMAN, "Cancelled"),
	},
	"Suspended": {
		# Restoration is the fastest path in the system and needs no approval.
		"Active": Transition("Active", ANY, "Restored"),
		"Cancelled": Transition("Cancelled", ANY, "Cancelled"),
	},
	"Cancelling": {
		"Active": Transition("Active", HUMAN, "Reactivated",
		                     note="The customer withdrew the cancellation."),
		"Cancelled": Transition("Cancelled", ANY, "Cancelled"),
	},
	"Cancelled": {
		"Active": Transition("Active", ANY, "Reactivated",
		                     note="Inside the reactivation window."),
		"Terminated": Transition("Terminated", ("Internal User",), "Terminated",
		                         needs_approval=True),
	},
	"Terminated": {},
}


def legal(from_state, to_state):
	"""The Transition for this move, or None."""
	return TABLE.get(from_state or "Draft", {}).get(to_state)


def allowed_targets(from_state):
	return sorted(TABLE.get(from_state or "Draft", {}))


def access_effect_for(state, policy_stage_effect=None):
	"""The access effect a state implies, unless the policy stage overrides it."""
	return policy_stage_effect or ACCESS_BY_STATE.get(state, "None")


# ------------------------------------------------------------------ the one mover
def transition(
	subscription,
	to_state,
	reason,
	triggered_by,
	actor=None,
	policy_stage=None,
	policy=None,
	access_effect=None,
	amount_at_risk=0,
	related=None,
	force=False,
):
	"""Move a subscription to `to_state`. The only sanctioned way to change state.

	Order matters and is not negotiable:

	1. Check the move is legal, or raise naming both states.
	2. If dry run is on, write the event marked `was_dry_run` and stop. Nothing changes.
	3. Write the Subscription Event.
	4. Apply the access effect.
	5. Update the subscription's own derived fields.
	6. Notify the tenant.

	The event is written before the effect on purpose. A crash between three and four
	leaves a record saying what was about to happen, which is recoverable. A crash between
	four and three leaves a customer switched off with nothing saying why, which is not.

	`force=True` is for an internal user acting deliberately against the table. It demands
	a reason, writes a Manual Override event, and must never be called from a scheduler.
	"""
	from a3_sola.api.lifecycle import access, events, notify

	doc = _as_doc(subscription)
	from_state = doc.status or "Draft"

	if not reason or not str(reason).strip():
		frappe.throw(_("A state change needs a reason. Every one of them is read by "
		               "somebody later."), title=_("Reason Required"))
	if triggered_by not in TRIGGERS:
		frappe.throw(_("{0} is not a recognised trigger.").format(triggered_by))

	if from_state == to_state:
		# Idempotent by design: the daily engine will ask for the state a subscription is
		# already in, every night, for as long as it stays there.
		return None

	move = legal(from_state, to_state)
	if not move and not force:
		frappe.throw(
			_("A subscription cannot go from {0} to {1}. Legal moves from {0} are: "
			  "{2}.").format(from_state, to_state, ", ".join(allowed_targets(from_state)) or _("none")),
			title=_("Illegal Transition"),
		)
	if move and triggered_by not in move.triggers and not force:
		frappe.throw(
			_("{0} to {1} cannot be triggered by {2}.").format(from_state, to_state, triggered_by),
			title=_("Illegal Transition"),
		)

	if force and triggered_by == "Scheduler":
		frappe.throw(
			_("A scheduler may never force a transition. Forcing is a person taking "
			  "responsibility for going outside the state machine."),
			title=_("Not Allowed"),
		)

	effect = access_effect or access_effect_for(to_state)
	dry_run = cint(get_value("dry_run_mode", 1))
	killed = cint(get_value("lifecycle_kill_switch", 0))
	inert = bool(dry_run or killed)

	event = events.record(
		subscription=doc,
		event_type="Manual Override" if force and not move else (move.event_type if move else "Manual Override"),
		from_state=from_state,
		to_state=to_state,
		reason=reason,
		triggered_by=triggered_by,
		actor=actor,
		policy=policy,
		policy_stage=policy_stage,
		access_effect_applied=effect,
		amount_at_risk=amount_at_risk,
		was_dry_run=inert,
		# Reversible when the state being entered can be left again. Suspended and
		# Cancelled both can; Terminated cannot, and the event says so.
		is_reversible=bool(allowed_targets(to_state)),
		related=related,
	)

	if inert:
		# Everything above still happened: the decision is computed, checked and written
		# down. Nothing below does.
		frappe.logger("a3_sola").info({
			"event": "lifecycle_transition_suppressed",
			"subscription": doc.name, "from": from_state, "to": to_state,
			"why": "kill switch" if killed else "dry run",
		})
		return event

	access.apply_access_effect(doc, effect, reason=reason, event=event)
	_write_state(doc, to_state, effect, policy=policy, policy_stage=policy_stage)
	notify.on_transition(doc, from_state, to_state, reason, event)
	return event


def _write_state(doc, to_state, effect, policy=None, policy_stage=None):
	"""Set the state and everything derived from it, in one write."""
	now = now_datetime()
	values = {
		"status": to_state,
		"access_state": EFFECT_TO_ACCESS_STATE.get(effect, "Full"),
		"state_since": now,
		"days_in_state": 0,
		"current_policy_stage": policy_stage or "",
	}
	if policy:
		values["policy"] = policy
	if to_state == "Suspended":
		values["suspension_count"] = cint(doc.get("suspension_count")) + 1
	doc.db_set(values, update_modified=False)
	doc.reload()


def refresh_derived(subscription):
	"""Recompute days_in_state and lifetime_days_active. Cheap, and run every night."""
	doc = _as_doc(subscription)
	values = {}
	if doc.state_since:
		values["days_in_state"] = max(0, date_diff(today(), getdate(doc.state_since)))
	if doc.start_date:
		values["lifetime_days_active"] = max(0, date_diff(today(), getdate(doc.start_date)))
	if values:
		doc.db_set(values, update_modified=False)
	return values


def _as_doc(subscription):
	if isinstance(subscription, str):
		return frappe.get_doc("Platform Subscription", subscription)
	return subscription
