# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The console: pre-flight checks, bulk operations, and one page per tenant.

The pre-flight check is the important thing here. Automatic suspension cannot be switched
on until every precondition is demonstrably in place, and each refusal names what is
missing. A client who turns this on with no default policy, no approval role and no
simulation behind them will suspend the wrong people in week one.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, now_datetime, today

from a3_sola.api import permissions
from a3_sola.api.settings import get_value

#: How many consecutive days the engine must have run before it is trusted to act.
MIN_HEARTBEAT_DAYS = 7


@frappe.whitelist()
def preflight():
	"""Every precondition for automatic suspension, each reported pass or fail."""
	checks = []

	policy = get_value("default_subscription_policy")
	valid = bool(policy and frappe.db.exists("Subscription Policy", policy))
	stages = 0
	if valid:
		stages = frappe.db.count("Policy Stage", {"parent": policy})
	checks.append(_check(
		"default_policy",
		_("A default subscription policy exists and has stages"),
		valid and stages > 0,
		_("{0} with {1} stage(s)").format(policy, stages) if valid
		else _("No default policy is set. The engine has nothing to apply."),
	))

	missing_templates = []
	if valid:
		# `parenttype` matters: without it a child-table query can match rows belonging
		# to a different doctype that happens to share a parent name.
		for row in frappe.get_all(
			"Policy Stage",
			filters={"parent": policy, "parenttype": "Subscription Policy"},
			fields=["stage_code", "notify_tenant", "notification_template"],
			order_by="idx asc",
		):
			if cint(row.notify_tenant) and not row.notification_template:
				missing_templates.append(row.stage_code)
	checks.append(_check(
		"notification_templates",
		_("Every stage that notifies has a template"),
		not missing_templates,
		_("These stages notify with no template and will send a plain message: {0}").format(
			", ".join(missing_templates)) if missing_templates else _("All present"),
	))

	limit = cint(get_value("max_suspensions_per_run", 0))
	checks.append(_check(
		"circuit_breaker", _("The circuit breaker limit is set"), limit > 0,
		_("Halts a run over {0} suspensions").format(limit) if limit
		else _("No limit set. One bug could suspend every customer in a single run."),
	))

	role = get_value("suspension_approval_role")
	holders = frappe.db.count("Has Role", {"role": role, "parenttype": "User"}) if role else 0
	checks.append(_check(
		"approval_role", _("The suspension approval role is set and somebody holds it"),
		bool(role and holders),
		_("{0}, held by {1} user(s)").format(role, holders) if role and holders
		else _("Nobody would receive a suspension to approve."),
	))

	last = _real_datetime(get_value("lifecycle_heartbeat_on"))
	streak = cint(get_value("lifecycle_heartbeat_streak_days", 0))
	fresh = bool(last and date_diff(today(), getdate(last)) <= 1)
	checks.append(_check(
		"heartbeat",
		_("The engine has run daily for at least {0} days").format(MIN_HEARTBEAT_DAYS),
		fresh and streak >= MIN_HEARTBEAT_DAYS,
		_("Last run {0}, {1} consecutive day(s)").format(last, streak) if last
		else _("The engine has never run."),
	))

	simulated = _real_datetime(get_value("lifecycle_simulation_last_run"))
	checks.append(_check(
		"simulation", _("The simulation has been run and read"), bool(simulated),
		_("Last simulated {0}").format(simulated) if simulated
		else _("Run the simulation and read every line before switching this on."),
	))

	return {
		"ready": all(c["passed"] for c in checks),
		"checks": checks,
		"note": _(
			"Automatic suspension stays off until every check passes. This is the last "
			"thing standing between a date-arithmetic bug and your customer base."
		),
	}


def _real_datetime(value):
	"""None for a value that only looks like a date.

	Clearing a Datetime on a Single reads back as the zero date rather than as nothing, and
	an engine that has never run would otherwise report "last run 0001-01-01" and pass the
	pre-flight check.
	"""
	if not value:
		return None
	text = str(value)
	return None if text.startswith("0001-01-01") or text.startswith("0000-00-00") else value


def _check(code, label, passed, detail):
	return {"code": code, "label": label, "passed": bool(passed), "detail": detail}


@frappe.whitelist()
def enable_automatic_suspension(confirm=None):
	"""Refuse until pre-flight passes, and name what is missing."""
	permissions.require_role("Platform Admin")
	result = preflight()
	if not result["ready"]:
		failures = [c["label"] for c in result["checks"] if not c["passed"]]
		frappe.throw(
			_("Automatic suspension cannot be switched on yet. Still to do: {0}.").format(
				"; ".join(failures)),
			title=_("Not Ready"),
		)
	if str(confirm or "").strip().upper() != "SUSPEND CUSTOMERS":
		frappe.throw(
			_('Type "SUSPEND CUSTOMERS" to confirm. From this point the engine can block '
			  'a paying customer\'s access without anybody watching.'),
			title=_("Confirm"),
		)
	frappe.db.set_single_value("A3 Sola Settings", {"enable_automatic_suspension": 1})
	frappe.log_error(
		title="a3_sola: automatic suspension ENABLED",
		message=f"Enabled by {frappe.session.user} at {now_datetime()}.",
	)
	return result


@frappe.whitelist()
def run_simulation():
	"""Every decision the engine would make, writing nothing. Stamps that it was run."""
	from a3_sola.api.lifecycle import engine

	permissions.require_role(("Platform Admin", "Platform Lifecycle Operator"),
	                         action="run the lifecycle simulation")
	summary = engine.simulate()
	frappe.db.set_single_value("A3 Sola Settings",
	                           {"lifecycle_simulation_last_run": now_datetime()})
	return summary


@frappe.whitelist()
def kill_switch(on=1, reason=None):
	"""Halt every lifecycle state change at once. Evaluation and logging carry on."""
	permissions.require_role("Platform Admin")
	if cint(on) and not reason:
		frappe.throw(_("Say why the kill switch is being pulled - it goes in the log."))
	frappe.db.set_single_value("A3 Sola Settings", {"lifecycle_kill_switch": cint(on)})
	frappe.log_error(
		title=f"a3_sola: lifecycle kill switch {'ON' if cint(on) else 'OFF'}",
		message=f"{frappe.session.user} at {now_datetime()}. {reason or ''}",
	)
	return cint(on)


# ------------------------------------------------------------ bulk operations
@frappe.whitelist()
def bulk_extend_grace(subscriptions, days, reason, confirm=None):
	"""For a gateway outage: push everybody's next state change out by N days.

	One event per subscription, never one for the batch - the question asked six months
	later is about one customer, and a batch record does not answer it.
	"""
	from a3_sola.api.lifecycle import events

	permissions.require_role(("Platform Admin", "Platform Lifecycle Operator"),
	                         action="extend grace in bulk")
	names = _names(subscriptions)
	_require_typed(confirm, "EXTEND", len(names))
	if not reason:
		frappe.throw(_("Extending grace needs a reason."))
	days = cint(days)
	if days <= 0 or days > 30:
		frappe.throw(_("Extend by between 1 and 30 days."))

	done = []
	for name in names:
		doc = frappe.get_doc("Platform Subscription", name)
		if doc.next_state_change_on:
			doc.db_set("next_state_change_on",
			           frappe.utils.add_days(doc.next_state_change_on, days),
			           update_modified=False)
		events.record(
			subscription=name, event_type="Manual Override",
			reason=_("Grace extended by {0} day(s): {1}").format(days, reason),
			triggered_by="Internal User", actor=frappe.session.user,
		)
		done.append(name)
	frappe.db.commit()
	return {"extended": done, "days": days}


@frappe.whitelist()
def bulk_restore(tenants, reason, confirm=None):
	"""After an incident: put everybody back. Each restoration is its own event."""
	from a3_sola.api.lifecycle import suspension as suspension_api

	permissions.require_role(("Platform Admin", "Platform Lifecycle Operator"),
	                         action="restore access in bulk")
	names = _names(tenants)
	_require_typed(confirm, "RESTORE", len(names))
	if not reason:
		frappe.throw(_("Restoring in bulk needs a reason."))
	done, failed = [], {}
	for name in names:
		try:
			suspension_api.restore(name, trigger="Manual", reason=reason)
			done.append(name)
		except Exception as exception:
			failed[name] = str(exception)[:160]
		frappe.db.commit()
	return {"restored": done, "failed": failed}


@frappe.whitelist()
def bulk_reassign_policy(subscriptions, policy, reason, confirm=None):
	from a3_sola.api.lifecycle import events

	permissions.require_role("Platform Admin")
	names = _names(subscriptions)
	_require_typed(confirm, "REASSIGN", len(names))
	if not frappe.db.exists("Subscription Policy", policy):
		frappe.throw(_("{0} is not a policy.").format(policy))
	for name in names:
		before = frappe.db.get_value("Platform Subscription", name, "policy")
		frappe.db.set_value("Platform Subscription", name, "policy", policy,
		                    update_modified=False)
		events.record(
			subscription=name, event_type="Manual Override",
			reason=_("Policy changed from {0} to {1}: {2}").format(
				before or _("none"), policy, reason),
			triggered_by="Internal User", actor=frappe.session.user,
		)
	frappe.db.commit()
	return {"reassigned": names, "policy": policy}


def _require_typed(confirm, word, count):
	if str(confirm or "").strip().upper() != word:
		frappe.throw(
			_('This affects {0} record(s). Type "{1}" to confirm.').format(count, word),
			title=_("Confirm"),
		)


def _names(value):
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.strip().startswith("[") else [value]
	names = [v for v in (value or []) if v]
	if not names:
		frappe.throw(_("Nothing was selected."))
	return names


# --------------------------------------------------------------- tenant 360
@frappe.whitelist()
def tenant_360(tenant):
	"""One page per tenant, so support answers a question without opening six doctypes."""
	from a3_sola.api.entitlements import TENANT_FIELD, get_tenant_usage
	from a3_sola.api.lifecycle import events

	permissions.require_role(
		("Platform Admin", "Platform Lifecycle Operator", "Platform Retention Manager",
		 "Platform Billing Manager", "Platform Tenant Manager"),
		action="open a tenant's record",
	)
	doc = frappe.get_doc("Tenant", tenant)
	subscription = (
		frappe.get_doc("Platform Subscription", doc.platform_subscription)
		if doc.platform_subscription else None
	)
	return {
		"tenant": {
			"name": doc.name, "tenant_name": doc.tenant_name, "status": doc.status,
			"access_gate": doc.get("access_gate"), "company": doc.company,
			"created": doc.creation,
		},
		"subscription": {
			"name": subscription.name, "plan": subscription.subscription_plan,
			"status": subscription.status, "access_state": subscription.access_state,
			"cycle": subscription.billing_cycle,
			"recurring_amount": flt(subscription.recurring_amount),
			"collection_route": subscription.collection_route,
			"next_billing_date": subscription.next_billing_date,
			"policy": subscription.policy,
			"policy_stage": subscription.current_policy_stage,
			"next_change_on": subscription.next_state_change_on,
			"next_change_to": subscription.next_state_change_to,
			"lifetime_value": flt(subscription.lifetime_value),
			"suspension_count": cint(subscription.suspension_count),
		} if subscription else None,
		"seats": get_tenant_usage(doc.name),
		"users": frappe.get_all(
			"User", filters={TENANT_FIELD: doc.name},
			fields=["name", "full_name", "enabled", "last_login", "last_active"],
			order_by="last_active desc",
		),
		"invoices": frappe.get_all(
			"Subscription Invoice",
			filters={"platform_subscription": doc.platform_subscription} if subscription else {"name": ""},
			fields=["name", "invoice_date", "due_date", "grand_total", "paid_amount",
			        "payment_status"],
			order_by="invoice_date desc", limit=12,
		),
		"suspensions": frappe.get_all(
			"Access Suspension", filters={"tenant": doc.name},
			fields=["name", "status", "reason", "applied_on", "restored_on",
			        "users_disabled_count"],
			order_by="creation desc", limit=10,
		),
		"changes": frappe.get_all(
			"Plan Change Request", filters={"tenant": doc.name},
			fields=["name", "request_type", "current_plan", "new_plan", "status",
			        "effective_date"],
			order_by="creation desc", limit=10,
		),
		"events": events.history(doc.platform_subscription, limit=25) if subscription else [],
		"onboarding": frappe.get_all(
			"Tenant Onboarding Task", filters={"parent": doc.name},
			fields=["task_code", "task_title", "is_critical", "is_complete"],
		),
	}
