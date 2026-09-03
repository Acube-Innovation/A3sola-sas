# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The suspension request, its approval queue, and the warning that must precede it.

A suspension is never applied by the code that decided it was due. The decision creates a
record; a person, or an explicitly configured absence of one, applies it. That separation
is the whole reason this file exists.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, get_url, getdate, now_datetime, today

from a3_sola.api.settings import get_value


def request_approval(plan):
	"""Create the Access Suspension a human has to approve, and take no other action."""
	from a3_sola.api.lifecycle import events, notify

	tenant = plan["tenant"]
	if not tenant:
		return None
	existing = frappe.db.get_value(
		"Access Suspension",
		{"tenant": tenant, "status": ["in", ["Pending Approval", "Scheduled"]],
		 "docstatus": ["<", 2]},
		"name",
	)
	if existing:
		return frappe.get_doc("Access Suspension", existing)

	warn_days = cint(get_value("notify_before_suspension_days", 3))
	doc = frappe.get_doc({
		"doctype": "Access Suspension",
		"tenant": tenant,
		"platform_subscription": plan["subscription"],
		"suspension_type": "Non Payment",
		"policy": plan["policy"],
		"policy_stage": plan["stage"],
		"reason": plan["reason"],
		"outstanding_amount": flt(plan["amount_at_risk"]),
		"requested_by": "Scheduler",
		"requested_on": now_datetime(),
		"scheduled_for": add_days(now_datetime(), warn_days),
		"approval_status": "Pending",
		"status": "Pending Approval",
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()

	events.record(
		subscription=plan["subscription"], event_type="Suspension Warned",
		reason=plan["reason"], triggered_by="Scheduler",
		from_state=plan["from_state"], to_state="Suspended",
		policy=plan["policy"], policy_stage=plan["stage"],
		amount_at_risk=flt(plan["amount_at_risk"]),
		related=("Access Suspension", doc.name),
	)
	send_warning(doc)
	notify.alert_internal(
		f"a3_sola: suspension awaiting approval - {tenant}",
		_queue_brief(doc),
		role=get_value("suspension_approval_role") or get_value("lifecycle_alert_role"),
	)
	return doc


def send_warning(suspension):
	"""The final warning: the exact date, the amount, and the one click that stops it."""
	from a3_sola.api.lifecycle import notify

	doc = _as_doc(suspension)
	if doc.warning_sent_on:
		return False
	subscription = frappe.get_doc("Platform Subscription", doc.platform_subscription)
	recipient = subscription.primary_contact_email
	if not recipient:
		return False
	when = frappe.utils.format_datetime(doc.scheduled_for)
	body = f"""
<p>Hello,</p>
<p>Access to A3 Sola for <b>{frappe.utils.escape_html(subscription.organisation_name or '')}</b>
will be paused on <b>{when}</b> unless the outstanding amount is settled.</p>
<p><b>Outstanding: {frappe.utils.fmt_money(flt(doc.outstanding_amount), currency=subscription.currency or 'INR')}</b></p>
<p>Paying stops this. Nothing will be deleted either way - your data, your users and their
permissions stay exactly as they are, and access comes back the moment payment clears.</p>
<p><a href="{get_url()}/billing">Pay now</a></p>
"""
	try:
		frappe.sendmail(recipients=[recipient], subject="Action needed: your A3 Sola access",
		                message=body, reference_doctype="Access Suspension",
		                reference_name=doc.name, now=bool(frappe.flags.in_test))
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: suspension warning {doc.name}")
		return False
	doc.db_set("warning_sent_on", now_datetime(), update_modified=False)
	return True


def warning_satisfied(suspension):
	"""Was the warning sent early enough? A suspension is refused if not.

	Same discipline as Phase 5's pre-debit notice, and for the same reason: a customer
	switched off without the notice they were promised is a customer who is entitled to be
	angry about it.
	"""
	doc = _as_doc(suspension)
	required = cint(get_value("notify_before_suspension_days", 3))
	if not required:
		return True, None
	if not doc.warning_sent_on:
		return False, _("No suspension warning has been sent. {0} days' notice is "
		                "required.").format(required)
	elapsed = date_diff(today(), getdate(doc.warning_sent_on))
	if elapsed < required:
		return False, _("The warning was sent {0} day(s) ago; {1} days' notice is "
		                "required.").format(elapsed, required)
	return True, None


@frappe.whitelist()
def approve(suspension, note=None):
	"""Apply a pending suspension. The warning gate is checked here, loudly."""
	from a3_sola.api.lifecycle import access, state_machine
	from a3_sola.api import permissions

	permissions.require_role(
		(get_value("suspension_approval_role") or "Platform Admin", "Platform Admin"),
		action="approve a suspension",
	)
	doc = _as_doc(suspension)
	if doc.approval_status == "Approved":
		return doc.name

	ok, why = warning_satisfied(doc)
	if not ok:
		frappe.throw(
			_("This suspension cannot be applied: {0}").format(why),
			title=_("Warning Not Given"),
		)

	doc.db_set({
		"approval_status": "Approved",
		"approved_by": frappe.session.user,
		"approved_on": now_datetime(),
		"status": "Scheduled",
		"reason_detail": note or doc.reason_detail,
	}, update_modified=False)

	subscription = frappe.get_doc("Platform Subscription", doc.platform_subscription)
	state_machine.transition(
		subscription, "Suspended", doc.reason, triggered_by="Internal User",
		actor=frappe.session.user, policy=doc.policy, policy_stage=doc.policy_stage,
		access_effect="Blocked", amount_at_risk=flt(doc.outstanding_amount),
		related=("Access Suspension", doc.name),
	)
	return doc.name


@frappe.whitelist()
def reject(suspension, reason):
	"""Cancel a pending suspension. The reason is mandatory and is written to the log."""
	from a3_sola.api.lifecycle import events
	from a3_sola.api import permissions

	permissions.require_role(
		(get_value("suspension_approval_role") or "Platform Admin", "Platform Admin"),
		action="reject a suspension",
	)
	if not reason or not str(reason).strip():
		frappe.throw(_("Rejecting a suspension needs a reason."))
	doc = _as_doc(suspension)
	doc.db_set({
		"approval_status": "Rejected",
		"status": "Cancelled",
		"rejection_reason": reason,
		"approved_by": frappe.session.user,
		"approved_on": now_datetime(),
	}, update_modified=False)
	events.record(
		subscription=doc.platform_subscription, event_type="Manual Override",
		reason=_("Suspension rejected: {0}").format(reason),
		triggered_by="Internal User", actor=frappe.session.user,
		policy=doc.policy, policy_stage=doc.policy_stage,
		related=("Access Suspension", doc.name),
	)
	return doc.name


@frappe.whitelist()
def restore(tenant, trigger="Manual", reason=None):
	"""One click, from anywhere. The payment webhook, the engine and the admin button all
	arrive here, and none of them needs an approval."""
	from a3_sola.api.lifecycle import access, state_machine

	name = frappe.db.get_value(
		"Access Suspension",
		{"tenant": tenant, "status": ["in", ["Applied", "Partially Applied"]]},
		"name", order_by="creation desc",
	)
	if name:
		access.restore_tenant_access(tenant, name, trigger=trigger,
		                             actor=frappe.session.user, reason=reason)
	subscription = frappe.db.get_value("Tenant", tenant, "platform_subscription")
	if subscription:
		doc = frappe.get_doc("Platform Subscription", subscription)
		if doc.status in ("Suspended", "Grace", "Past Due"):
			state_machine.transition(
				doc, "Active", reason or _("Access restored ({0}).").format(trigger),
				triggered_by="Webhook" if trigger == "Payment Received" else "Internal User",
				actor=frappe.session.user,
			)
	return True


def restore_if_suspended(plan):
	"""Used by the engine's restoration pass, before the state transition."""
	from a3_sola.api.lifecycle import access

	tenant = plan.get("tenant")
	if not tenant:
		return None
	name = frappe.db.get_value(
		"Access Suspension",
		{"tenant": tenant, "status": ["in", ["Applied", "Partially Applied"]]},
		"name", order_by="creation desc",
	)
	if not name:
		return None
	return access.restore_tenant_access(tenant, name, trigger="Payment Received",
	                                    reason=plan["reason"])


def approval_queue():
	"""Everything a person needs to decide in ten seconds, in one row per suspension."""
	rows = frappe.get_all(
		"Access Suspension",
		filters={"status": "Pending Approval", "docstatus": 1},
		fields=["name", "tenant", "platform_subscription", "reason", "outstanding_amount",
		        "scheduled_for", "warning_sent_on", "requested_on", "policy_stage"],
		order_by="scheduled_for asc",
	)
	for row in rows:
		subscription = row.platform_subscription
		row["days_overdue"] = _days_overdue(subscription)
		row["lifetime_value"] = flt(frappe.db.get_value(
			"Platform Subscription", subscription, "lifetime_value"))
		row["last_payment"] = frappe.db.get_value(
			"Platform Subscription", subscription, "last_successful_billing_date")
		row["dunning_attempts"] = frappe.db.count(
			"Dunning Attempt", {"parent": subscription})
		row["warning_ok"], row["warning_problem"] = warning_satisfied(row["name"])
	return rows


def remind_pending():
	"""Daily. Inaction never applies a suspension - it produces a reminder."""
	from a3_sola.api.lifecycle import notify

	due = frappe.get_all(
		"Access Suspension",
		filters={"status": "Pending Approval", "docstatus": 1,
		         "scheduled_for": ["<=", now_datetime()]},
		fields=["name", "tenant", "outstanding_amount", "scheduled_for"],
	)
	if not due:
		return 0
	listing = "\n".join(
		f"  {r.name}  {r.tenant}  due {r.scheduled_for}  outstanding {flt(r.outstanding_amount)}"
		for r in due
	)
	notify.alert_internal(
		f"a3_sola: {len(due)} suspension(s) waiting on a decision",
		"These passed their scheduled date and were NOT applied - nothing is suspended "
		"without somebody approving it:\n\n" + listing,
		role=get_value("suspension_approval_role") or get_value("lifecycle_alert_role"),
	)
	return len(due)


def _queue_brief(suspension):
	doc = _as_doc(suspension)
	return (
		f"Tenant: {doc.tenant}\n"
		f"Outstanding: {flt(doc.outstanding_amount)}\n"
		f"Days overdue: {_days_overdue(doc.platform_subscription)}\n"
		f"Scheduled for: {doc.scheduled_for}\n"
		f"Reason: {doc.reason}\n\n"
		f"Nothing has happened yet. Approve it in the queue, or reject it with a reason."
	)


def _days_overdue(subscription):
	if not subscription:
		return 0
	due = frappe.db.get_value("Platform Subscription", subscription, "next_billing_date")
	return max(0, date_diff(today(), getdate(due))) if due else 0


def _as_doc(suspension):
	if isinstance(suspension, str):
		return frappe.get_doc("Access Suspension", suspension)
	return suspension
