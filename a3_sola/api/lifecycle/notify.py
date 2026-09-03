# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Telling the tenant what happened to their subscription.

Never change access without notifying the tenant. That is one of the three rules of this
phase, and this is where it is kept.

Delivery is deliberately forgiving: a mail server that is down must not roll back a state
change that has already been decided, written and applied. Failures are logged against the
event, and the event says whether the notification went out.
"""

import frappe
from frappe.utils import flt, fmt_money, get_url

from a3_sola.api.settings import get_value

#: What the tenant is told, per state. Plain language on purpose - a customer who can read
#: why something happened raises fewer tickets.
SUBJECTS = {
	"Past Due": "Your payment did not go through",
	"Grace": "Action needed on your A3 Sola subscription",
	"Suspended": "Your A3 Sola access has been paused",
	"Active": "Your A3 Sola access is back on",
	"Cancelling": "Your cancellation is scheduled",
	"Cancelled": "Your A3 Sola subscription has ended",
	"Trialing": "Your A3 Sola trial has started",
}


def on_transition(subscription, from_state, to_state, reason, event=None):
	"""Send the tenant the message this transition calls for."""
	from a3_sola.api.lifecycle import events

	recipient = subscription.get("primary_contact_email")
	if not recipient:
		frappe.logger("a3_sola").info(
			{"event": "lifecycle_notify_skipped", "subscription": subscription.name,
			 "why": "no contact email"}
		)
		return False

	subject = SUBJECTS.get(to_state)
	if not subject:
		# Not every transition is worth an email. Trial Ended into Pending Payment is
		# already covered by the renewal notices.
		return False

	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			message=_body(subscription, to_state, reason),
			reference_doctype="Platform Subscription",
			reference_name=subscription.name,
			now=bool(frappe.flags.in_test),
		)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"a3_sola: lifecycle notification for {subscription.name}",
		)
		return False

	events.mark_notified(event)
	return True


def _body(subscription, to_state, reason):
	pay_now = f"{get_url()}/billing"
	outstanding = flt(subscription.get("recurring_amount"))
	money = fmt_money(outstanding, currency=subscription.get("currency") or "INR")

	if to_state == "Suspended":
		return f"""
<p>Hello,</p>
<p>Access to A3 Sola for <b>{frappe.utils.escape_html(subscription.organisation_name or "")}</b>
has been paused because {frappe.utils.escape_html(reason)}.</p>
<p><b>Outstanding: {money}</b></p>
<p>Nothing has been deleted. Your data, your users and their permissions are exactly as
you left them. Paying restores access immediately - not after a support ticket, and not
the next morning.</p>
<p><a href="{pay_now}">Pay now and restore access</a></p>
"""
	if to_state == "Grace":
		return f"""
<p>Hello,</p>
<p>We have not been able to collect {money} for your A3 Sola subscription.</p>
<p>You still have full access. If this is not settled, access will be restricted - the
exact date is shown on your billing page, and you will get a warning before anything
changes.</p>
<p><a href="{pay_now}">Settle now</a></p>
"""
	if to_state == "Active":
		return f"""
<p>Hello,</p>
<p>Your A3 Sola access is back on. Everyone who was signed in before can sign in again,
with the same permissions.</p>
<p>Reason: {frappe.utils.escape_html(reason)}</p>
"""
	return f"""
<p>Hello,</p>
<p>Your A3 Sola subscription is now <b>{to_state}</b>.</p>
<p>Reason: {frappe.utils.escape_html(reason)}</p>
<p><a href="{pay_now}">Your billing page</a></p>
"""


def alert_internal(subject, message, role=None):
	"""Tell the people who watch this engine. Never silently."""
	role = role or get_value("lifecycle_alert_role")
	frappe.log_error(title=subject, message=message)
	if not role:
		return False
	recipients = frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"
	)
	recipients = [
		r for r in recipients
		if frappe.db.get_value("User", r, "enabled") and "@" in (r or "")
	]
	if not recipients:
		return False
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=message,
		                now=bool(frappe.flags.in_test))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: lifecycle alert could not be sent")
		return False
	return True
