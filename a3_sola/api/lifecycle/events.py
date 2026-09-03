# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Writing to the immutable event log.

One function. Everything in Phase 7 that changes anything calls it, and nothing writes a
Subscription Event any other way - which is what makes the log complete enough to answer
"why was this customer suspended" from a single search.
"""

import frappe
from frappe.utils import flt, now_datetime

from a3_sola.api.sanitise import clean_text


def record(
	subscription,
	event_type,
	reason,
	triggered_by="Scheduler",
	from_state=None,
	to_state=None,
	actor=None,
	policy=None,
	policy_stage=None,
	access_effect_applied=None,
	amount_at_risk=0,
	was_dry_run=0,
	is_reversible=1,
	notification_sent=0,
	reason_detail=None,
	related=None,
):
	"""Write one event and return it.

	`related` is a (doctype, name) pair for the document that caused this - a suspension,
	a plan change, a payment order.
	"""
	name = subscription if isinstance(subscription, str) else subscription.name
	doc = frappe.new_doc("Subscription Event")
	doc.update({
		"platform_subscription": name,
		"event_type": event_type,
		"event_time": now_datetime(),
		"from_state": from_state,
		"to_state": to_state,
		"triggered_by": triggered_by,
		"actor": actor or frappe.session.user,
		"policy": policy,
		"policy_stage": policy_stage,
		# Sanitised, because these two are the only fields in the lifecycle a customer
		# types into - the cancellation reason and its detail - and they leave again in
		# an email, a report and a CSV export. See a3_sola/api/sanitise.py.
		"reason": clean_text(reason, 500),
		"reason_detail": clean_text(reason_detail),
		"access_effect_applied": access_effect_applied,
		# flt, always: a None here and a 0.0 there is how a comparison that should be
		# equal quietly is not.
		"amount_at_risk": flt(amount_at_risk),
		"was_dry_run": 1 if was_dry_run else 0,
		"is_reversible": 1 if is_reversible else 0,
		"notification_sent": 1 if notification_sent else 0,
	})
	if related:
		doc.related_doctype, doc.related_name = related
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def mark_notified(event):
	"""The event log is append-only, and this is the one field that is set after the fact.

	It is written with `db_set` rather than a save because a save would be refused. The
	value is a delivery receipt, not a change to what the event says happened.
	"""
	if not event:
		return
	name = event if isinstance(event, str) else event.name
	frappe.db.set_value("Subscription Event", name, "notification_sent", 1,
	                    update_modified=False)


def link_reversal(original, reversing):
	"""Point an event at the one that undoes it. Same reasoning as `mark_notified`."""
	if not (original and reversing):
		return
	frappe.db.set_value(
		"Subscription Event",
		original if isinstance(original, str) else original.name,
		"reversal_event",
		reversing if isinstance(reversing, str) else reversing.name,
		update_modified=False,
	)


def history(subscription, limit=50):
	"""Newest first. Used by the portal, the Tenant 360 view and the audit report."""
	return frappe.get_all(
		"Subscription Event",
		filters={"platform_subscription": subscription},
		fields=["name", "event_time", "event_type", "from_state", "to_state", "reason",
		        "triggered_by", "actor", "was_dry_run", "policy_stage", "amount_at_risk"],
		order_by="event_time desc, creation desc",
		limit=limit,
	)
