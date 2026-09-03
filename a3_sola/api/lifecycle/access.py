# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Blocking and restoring a tenant's access, reversibly.

THE REQUIREMENT THAT DICTATES THE DESIGN

A tenant pays their overdue invoice at 11pm. They must be working at 11:01pm - not after a
support ticket the next morning. So suspension disables access WITHOUT DESTROYING STATE:

* Never delete a User.
* Never remove a Role or a Role Profile.
* Never delete a User Permission.
* Never touch tenant business data.

What is changed is `User.enabled`, and what it was before is written down first. Anything
that cannot be restored byte-for-byte is not changed at all.

THE EXCLUSIONS ARE THE DANGEROUS PART

Resolving "the users of this tenant" wrongly is how you disable your own staff, or another
customer. So the resolution fails closed: if the set is empty, or contains anybody it
should not, the whole suspension is abandoned and an alert goes out. Disabling nobody and
shouting about it is always recoverable. Disabling the wrong people is not.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from a3_sola.api.entitlements import INTERNAL_PLATFORM_ROLES, TENANT_FIELD
from a3_sola.api.settings import get_value

#: Users no suspension may ever touch, whatever the tenant resolution says.
NEVER_DISABLE = ("Administrator", "Guest")


# --------------------------------------------------------------- resolution
def tenant_users(tenant):
	"""Every User stamped with this tenant, with the fields a snapshot needs."""
	return frappe.get_all(
		"User",
		filters={TENANT_FIELD: tenant},
		fields=["name", "full_name", "enabled", "last_active"],
		order_by="creation asc",
	)


def excluded_reason(user_row, tenant):
	"""Why this user must not be disabled, or None if they may be.

	Every branch here has a test. The comment on each is the reason it exists.
	"""
	name = user_row.get("name")
	if name in NEVER_DISABLE:
		# The account that fixes a broken suspension must never be caught by one.
		return _("{0} is a system account").format(name)

	stamp = frappe.db.get_value("User", name, TENANT_FIELD)
	if not stamp:
		# Your own staff carry no tenant stamp. A resolution bug that returns them is the
		# single worst outcome here, so it is checked again at the point of action rather
		# than trusted from the query.
		return _("{0} carries no tenant stamp - internal staff are never suspended").format(name)
	if stamp != tenant:
		return _("{0} belongs to tenant {1}, not {2}").format(name, stamp, tenant)

	roles = set(frappe.get_roles(name))
	held = roles & set(INTERNAL_PLATFORM_ROLES)
	if held:
		# A customer user should never hold one of these. If one does, that is a
		# provisioning bug and disabling them would hide it.
		return _("{0} holds the internal role {1}").format(name, ", ".join(sorted(held)))
	return None


def resolve_for_suspension(tenant):
	"""(users to disable, refusals). A non-empty refusal list means: do nothing."""
	rows = tenant_users(tenant)
	if not rows:
		return [], [_("No users are stamped with tenant {0}. Refusing to suspend a tenant "
		              "whose user set could not be resolved.").format(tenant)]
	safe, refusals = [], []
	for row in rows:
		why = excluded_reason(row, tenant)
		if why:
			refusals.append(why)
		else:
			safe.append(row)
	return safe, refusals


# --------------------------------------------------------------- suspension
def suspend_tenant_access(tenant, suspension):
	"""Disable every user of a tenant, having first written down how to put it back.

	Returns the suspension document. Raises only for a resolution failure - a per-user
	failure is recorded and reported as Partially Applied, never as success.
	"""
	from a3_sola.api.lifecycle import events, notify

	doc = suspension if not isinstance(suspension, str) else frappe.get_doc(
		"Access Suspension", suspension
	)
	tenant_name = tenant if isinstance(tenant, str) else tenant.name

	users, refusals = resolve_for_suspension(tenant_name)
	if refusals or not users:
		detail = "\n".join(refusals)
		doc.db_set({"status": "Failed", "reason_detail": detail}, update_modified=False)
		notify.alert_internal(
			f"a3_sola: suspension of {tenant_name} abandoned",
			"The user set for this tenant could not be resolved safely, so nobody was "
			"disabled:\n\n" + detail,
		)
		frappe.throw(
			_("Refusing to suspend {0}: {1}").format(tenant_name, detail),
			title=_("Suspension Abandoned"),
		)

	# 1. Snapshot, and COMMIT IT, before touching anybody. A crash on the third user must
	#    still leave a complete record of what the first two were.
	doc.set("affected_users", [])
	for row in users:
		doc.append("affected_users", {
			"user": row["name"],
			"user_full_name": row.get("full_name"),
			"was_enabled": 1 if row.get("enabled") else 0,
			"had_roles": json.dumps(sorted(frappe.get_roles(row["name"]))),
			"last_active_on": row.get("last_active"),
		})
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# 2. Disable them one at a time, recording each outcome.
	disabled, failures = 0, []
	for snap in doc.affected_users:
		try:
			if snap.was_enabled:
				_set_enabled(snap.user, 0)
				disabled += 1
			_terminate_sessions(snap.user)
		except Exception as exception:
			snap.db_set("restore_error", f"disable failed: {str(exception)[:120]}",
			            update_modified=False)
			failures.append(f"{snap.user}: {exception}")

	status = "Partially Applied" if failures else "Applied"
	event = events.record(
		subscription=doc.platform_subscription,
		event_type="Suspended",
		reason=doc.reason,
		reason_detail=doc.reason_detail,
		triggered_by="Scheduler" if doc.requested_by == "Scheduler" else "Internal User",
		to_state="Suspended",
		policy=doc.policy,
		policy_stage=doc.policy_stage,
		access_effect_applied="Blocked",
		amount_at_risk=flt(doc.outstanding_amount),
		related=("Access Suspension", doc.name),
	)
	doc.db_set({
		"status": status,
		"applied_on": now_datetime(),
		"users_disabled_count": disabled,
		"subscription_event": event.name,
	}, update_modified=False)
	set_gate(tenant_name, "Blocked")

	if failures:
		notify.alert_internal(
			f"a3_sola: suspension of {tenant_name} only partly applied",
			"These users could not be disabled:\n\n" + "\n".join(failures),
		)
	_tell_the_customer(doc, tenant_name)
	return doc


def restore_tenant_access(tenant, suspension, trigger="Manual", actor=None, reason=None):
	"""Put every snapshotted user back to the state it was recorded in.

	Recorded state, not "enabled". A user the tenant had themselves disabled before the
	suspension must stay disabled - restoring them would hand access to somebody the
	customer had deliberately removed.

	No approval, no scheduler, no queue. This is the fastest path in the system.
	"""
	from a3_sola.api.lifecycle import events, notify

	doc = suspension if not isinstance(suspension, str) else frappe.get_doc(
		"Access Suspension", suspension
	)
	tenant_name = tenant if isinstance(tenant, str) else tenant.name

	if doc.status == "Restored":
		return doc  # idempotent: a webhook and the engine may both arrive

	failures = []
	for snap in doc.affected_users:
		try:
			_set_enabled(snap.user, 1 if snap.was_enabled else 0)
			snap.db_set({"restored": 1, "restored_on": now_datetime(), "restore_error": ""},
			            update_modified=False)
		except Exception as exception:
			snap.db_set("restore_error", str(exception)[:140], update_modified=False)
			failures.append(f"{snap.user}: {exception}")

	event = events.record(
		subscription=doc.platform_subscription,
		event_type="Restored",
		reason=reason or _("Access restored: {0}").format(trigger),
		triggered_by="Webhook" if trigger == "Payment Received" else "Internal User",
		actor=actor,
		to_state="Active",
		access_effect_applied="None",
		related=("Access Suspension", doc.name),
	)
	events.link_reversal(doc.subscription_event, event)
	doc.db_set({
		"status": "Restored" if not failures else "Partially Applied",
		"restored_on": now_datetime(),
		"restored_by": actor or frappe.session.user,
		"restoration_trigger": trigger,
		"restoration_reason": reason or trigger,
	}, update_modified=False)
	clear_gate(tenant_name)

	if failures:
		notify.alert_internal(
			f"a3_sola: restoration of {tenant_name} incomplete",
			"These users could not be restored:\n\n" + "\n".join(failures),
		)
	return doc


def _set_enabled(user, enabled):
	"""Flip one user's enabled flag, and nothing else.

	`db_set` on the document rather than a save: saving a User runs the seat-quota
	validation in `entitlements.before_user_save`, and a restoration must never be blocked
	by a quota check on users who were already inside the quota when they were disabled.
	"""
	frappe.db.set_value("User", user, "enabled", cint(enabled), update_modified=False)
	frappe.clear_cache(user=user)


def _terminate_sessions(user):
	"""Suspension takes effect now, not at next login."""
	frappe.db.delete("Sessions", {"user": user})


def _tell_the_customer(suspension, tenant_name):
	"""The billing contact cannot read this in the app - they are disabled. It goes by
	email, and it says the amount, how to pay, and that paying restores access at once."""
	from a3_sola.api.lifecycle import notify

	subscription = suspension.platform_subscription
	if not subscription:
		return
	doc = frappe.get_doc("Platform Subscription", subscription)
	sent = notify.on_transition(doc, "Grace", "Suspended", suspension.reason,
	                            suspension.subscription_event)
	if sent:
		suspension.db_set("notification_sent_on", now_datetime(), update_modified=False)


# ------------------------------------------------------------- softer states
def apply_access_effect(subscription, effect, reason=None, event=None):
	"""Apply one of the four access effects to a subscription's tenant.

	None        no change at all
	Banner Only a persistent notice; work is not obstructed
	Read Only   read and report stay open, submit/cancel/amend are refused
	Blocked     full suspension, through the path above
	"""
	tenant = _tenant_of(subscription)
	if not tenant:
		return None
	if effect in (None, "", "None"):
		clear_gate(tenant)
		return "None"
	if effect in ("Banner Only", "Read Only"):
		set_gate(tenant, "Banner" if effect == "Banner Only" else "Read Only")
		return effect
	if effect == "Blocked":
		suspension = _open_suspension_for(subscription, tenant, reason)
		suspend_tenant_access(tenant, suspension)
		return effect
	frappe.throw(_("{0} is not an access effect.").format(effect))


def _open_suspension_for(subscription, tenant, reason):
	"""The Access Suspension a Blocked effect needs, if one is not already open."""
	existing = frappe.db.get_value(
		"Access Suspension",
		{"tenant": tenant, "status": ["in", ["Scheduled", "Pending Approval", "Draft"]],
		 "docstatus": ["<", 2]},
		"name",
	)
	if existing:
		return frappe.get_doc("Access Suspension", existing)
	doc = frappe.get_doc({
		"doctype": "Access Suspension",
		"tenant": tenant,
		"platform_subscription": subscription.name if not isinstance(subscription, str) else subscription,
		"suspension_type": "Non Payment",
		"reason": reason or _("Non payment"),
		"requested_by": "Scheduler",
		"requested_on": now_datetime(),
		"approval_status": "Not Required",
		"status": "Scheduled",
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


# ---------------------------------------------------------------- the gate
#: Held on the Tenant rather than in a cache, so it survives a restart and so support can
#: read a tenant's gate state from the record rather than from a redis key.
GATE_FIELD = "access_gate"


def set_gate(tenant, state):
	frappe.db.set_value("Tenant", tenant, GATE_FIELD, state, update_modified=False)
	_invalidate(tenant)
	return state


def clear_gate(tenant):
	frappe.db.set_value("Tenant", tenant, GATE_FIELD, "Full", update_modified=False)
	_invalidate(tenant)
	return "Full"


def gate_state(tenant):
	return frappe.db.get_value("Tenant", tenant, GATE_FIELD) or "Full"


def _invalidate(tenant):
	"""Drop the cached per-user gate for everyone in this tenant.

	The gate is read on every request, so it is cached per user. Any state change has to
	clear it, or a restored customer stays locked out until the cache expires - which is
	the same bug as not restoring them at all.

	Delegated to the gate rather than reaching into the cache here, so the key exists in
	exactly one place. Two copies of a cache key is how a restoration quietly stops
	working six months after somebody renames one of them.
	"""
	from a3_sola.api.lifecycle import gate

	gate.invalidate(tenant=tenant)


def _tenant_of(subscription):
	if isinstance(subscription, str):
		subscription = frappe.get_doc("Platform Subscription", subscription)
	return frappe.db.get_value("Tenant", {"platform_subscription": subscription.name}, "name")


def set_tenant_access_state(tenant, state, reason):
	"""The Phase 6 extension point, implemented.

	Phase 6 defined this as the one funnel for every access change after provisioning. It
	stays that, and delegates: the Tenant status is set here, the user-level work goes
	through the suspension path so it is snapshotted and reversible like everything else.
	"""
	from a3_sola.api.lifecycle import events

	tenant_name = tenant if isinstance(tenant, str) else tenant.name
	current = frappe.db.get_value("Tenant", tenant_name, "status")
	if current == state:
		return False  # idempotent - the daily job asks for this repeatedly

	subscription = frappe.db.get_value(
		"Tenant", tenant_name, "platform_subscription"
	)
	frappe.db.set_value("Tenant", tenant_name,
	                    {"status": state, "status_reason": reason}, update_modified=False)

	if state in ("Suspended", "Cancelled", "Terminated"):
		if subscription:
			apply_access_effect(subscription, "Blocked", reason=reason)
		else:
			set_gate(tenant_name, "Blocked")
	elif state == "Active":
		open_suspension = frappe.db.get_value(
			"Access Suspension",
			{"tenant": tenant_name, "status": ["in", ["Applied", "Partially Applied"]]},
			"name",
		)
		if open_suspension:
			restore_tenant_access(tenant_name, open_suspension, trigger="Policy",
			                      reason=reason)
		else:
			clear_gate(tenant_name)

	if subscription:
		events.record(
			subscription=subscription,
			event_type="Manual Override" if state not in ("Suspended", "Active") else (
				"Suspended" if state == "Suspended" else "Restored"),
			reason=reason,
			triggered_by="Internal User",
			from_state=current,
			to_state=state,
		)
	return True
