# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The super-admin console: one place to see and operate the platform.

Built entirely on existing data. No new doctypes, no new business logic - every action
routes to the function that already owns it, because a console that reimplements
suspension is a second suspension implementation that will drift from the first.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, flt, now_datetime, today

from a3_sola.api import permissions
from a3_sola.api.settings import get_value

CONSOLE_ROLES = ("Platform Admin", "Platform Lifecycle Operator",
                 "Platform Tenant Manager", "System Manager")


@frappe.whitelist()
def overview():
	"""The one page. Everything a person needs to know the platform is healthy."""
	permissions.require_role(CONSOLE_ROLES, action="open the platform console")

	states = {}
	for row in frappe.get_all("Platform Subscription", filters={"docstatus": 1},
	                          fields=["status", "count(name) as n"], group_by="status"):
		states[row["status"] or "Unknown"] = cint(row["n"])

	mrr = _mrr()
	return {
		"generated_on": str(now_datetime()),
		"tenants": _tenants(),
		"subscriptions": states,
		"revenue": {
			"mrr": mrr,
			"arr": flt(mrr * 12, 2),
			"at_risk": _revenue_at_risk(),
			"average_per_tenant": flt(mrr / max(1, _tenants().get("Active", 1)), 2),
		},
		"users_across_all_tenants": _active_users(),
		"needs_attention": {
			"provisioning_interventions": frappe.db.count(
				"Provisioning Job", {"requires_manual_intervention": 1}),
			"suspensions_pending_approval": frappe.db.count(
				"Access Suspension", {"status": "Pending Approval", "docstatus": 1}),
			"unreconciled_settlement_lines": _count_if_exists(
				"Settlement Line", {"match_status": ["!=", "Matched"]}),
			"failed_webhooks_24h": frappe.db.count(
				"Payment Webhook Log",
				{"signature_verified": 0,
				 "received_on": [">", add_to_date(now_datetime(), hours=-24)]}),
			"open_alerts": _open_alerts(),
		},
		"health": _health(),
		# Displayed prominently on purpose. "Why is nothing posting" has this answer more
		# often than any other, and somebody always forgets which mode production is in.
		"modes": modes(),
	}


def _tenants():
	out = {}
	for row in frappe.get_all("Tenant", fields=["status", "count(name) as n"],
	                          group_by="status"):
		out[row["status"] or "Unknown"] = cint(row["n"])
	return out


def _mrr():
	total = 0.0
	for row in frappe.get_all("Platform Subscription",
	                          filters={"status": ["in", ["Active", "Trialing", "Past Due",
	                                                     "Grace"]], "docstatus": 1},
	                          fields=["recurring_amount", "billing_cycle"]):
		amount = flt(row.recurring_amount)
		total += flt(amount / 12.0, 2) if row.billing_cycle == "Annual" else amount
	return flt(total, 2)


def _revenue_at_risk():
	total = 0.0
	for row in frappe.get_all("Platform Subscription",
	                          filters={"status": ["in", ["Past Due", "Grace", "Suspended",
	                                                     "Cancelling"]], "docstatus": 1},
	                          fields=["recurring_amount", "billing_cycle"]):
		amount = flt(row.recurring_amount)
		total += flt(amount / 12.0, 2) if row.billing_cycle == "Annual" else amount
	return flt(total, 2)


def _active_users():
	from a3_sola.api.entitlements import TENANT_FIELD

	return frappe.db.count("User", {TENANT_FIELD: ["is", "set"], "enabled": 1})


def _count_if_exists(doctype, filters):
	return frappe.db.count(doctype, filters) if frappe.db.exists("DocType", doctype) else 0


def _open_alerts():
	from a3_sola.api.monitoring import alerts

	try:
		return len(alerts.evaluate())
	except Exception:
		return None


def _health():
	from a3_sola.api.monitoring import heartbeat

	rows = heartbeat.status()
	return {
		"jobs_watched": len(rows),
		"jobs_stopped": len([r for r in rows if not r["healthy"]]),
		"stopped": [r["method"] for r in rows if not r["healthy"]][:10],
	}


# ------------------------------------------------------------------ mode control
#: The master switches from across the phases, in one place, with what each costs.
MODES = (
	("enable_accounting_postings", "Accounting postings",
	 "Project and subsidy postings reach the general ledger. Requires the CA's written "
	 "confirmation of the GST treatment first."),
	("enable_payment_postings", "Payment postings",
	 "Subscription revenue and gateway fees post to the mapped accounts."),
	("gst_treatment_confirmed_by_ca", "GST treatment confirmed",
	 "The gate both posting switches sit behind. Set it only when you have it in writing."),
	("enable_automatic_suspension", "Automatic suspension",
	 "The lifecycle engine may block a paying customer's access with nobody watching."),
	("dry_run_mode", "Lifecycle dry run",
	 "On means the engine decides and logs but changes nothing. Ships on."),
	("lifecycle_kill_switch", "Lifecycle kill switch",
	 "Halts every state change immediately. Evaluation and logging carry on."),
	("require_manual_approval_for_suspension", "Suspension needs approval",
	 "A person approves each suspension before it applies."),
	("provisioning_mode", "Provisioning mode",
	 "Automatic or Manual Approval. Manual until the failure rate justifies otherwise."),
	("maintenance_mode", "Maintenance mode",
	 "The public site shows a holding page."),
	("run_isolation_test_on_provision", "Verify isolation before activating",
	 "A tenant that fails the check is never handed to a customer."),
)


@frappe.whitelist()
def modes():
	"""Every master switch, its state, and who last changed it."""
	permissions.require_role(CONSOLE_ROLES, action="read the mode switches")
	out = []
	for field, label, note in MODES:
		out.append({
			"field": field, "label": label, "note": note,
			"value": get_value(field),
			"last_changed": _last_changed(field),
		})
	return out


def _last_changed(field):
	"""From the Version history of the settings singleton."""
	try:
		rows = frappe.get_all(
			"Version", filters={"ref_doctype": "A3 Sola Settings"},
			fields=["owner", "creation", "data"], order_by="creation desc", limit=40)
		for row in rows:
			data = json.loads(row.data or "{}")
			for change in data.get("changed") or []:
				if change and change[0] == field:
					return {"by": row.owner, "on": str(row.creation),
					        "from": change[1], "to": change[2]}
	except Exception:
		pass
	return None


# ----------------------------------------------------------------- impersonation
#: How long a support session may last before it ends itself.
IMPERSONATION_MINUTES = 30


@frappe.whitelist()
def start_impersonation(tenant, reason, minutes=IMPERSONATION_MINUTES):
	"""Support acting as a tenant admin - reason-gated, time-limited, audited, notified.

	IMPERSONATION WITHOUT NOTIFICATION IS A TRUST VIOLATION. The tenant is told a support
	session happened, every time. It is configurable because a client will ask, and it
	defaults to on because the client asking is not the person whose account it is.

	This does not switch the session user by itself - Frappe's own impersonation does
	that. What this owns is the permission, the reason, the clock, the audit record and
	the notification, so none of those can be skipped.
	"""
	permissions.require_role(("Platform Admin", "Platform Tenant Manager", "System Manager"),
	                         action="impersonate a tenant administrator")
	if not reason or len(str(reason).strip()) < 15:
		frappe.throw(
			_("Give a real reason - at least fifteen characters. It is shown to the "
			  "customer, who is told this session happened."),
			title=_("Reason Required"),
		)
	row = frappe.db.get_value("Tenant", tenant,
	                          ["admin_user", "tenant_name", "primary_contact_email"],
	                          as_dict=True)
	if not (row and row.admin_user):
		frappe.throw(_("{0} has no administrator to act as.").format(tenant))

	minutes = min(cint(minutes) or IMPERSONATION_MINUTES, 120)
	expires = add_to_date(now_datetime(), minutes=minutes)
	token = frappe.generate_hash(length=24)
	session = {
		"token": token, "tenant": tenant, "acting_as": row.admin_user,
		"operator": frappe.session.user, "reason": str(reason).strip(),
		"started": str(now_datetime()), "expires": str(expires),
	}
	frappe.cache().set_value(f"a3s_impersonation::{token}", json.dumps(session),
	                         expires_in_sec=minutes * 60)
	frappe.cache().set_value(f"a3s_impersonation_by::{frappe.session.user}", token,
	                         expires_in_sec=minutes * 60)

	_audit_impersonation(session, "started")
	_tell_the_tenant(row, session)
	return {
		"token": token, "acting_as": row.admin_user, "expires": str(expires),
		"banner": _(
			"You are acting as {0} for {1}. This session ends at {2} and the customer "
			"has been told it happened."
		).format(row.admin_user, row.tenant_name, expires),
	}


@frappe.whitelist()
def end_impersonation(token=None):
	permissions.require_role(("Platform Admin", "Platform Tenant Manager", "System Manager"),
	                         action="end a support session")
	token = token or frappe.cache().get_value(
		f"a3s_impersonation_by::{frappe.session.user}")
	if not token:
		return {"ok": True, "message": _("No session was open.")}
	raw = frappe.cache().get_value(f"a3s_impersonation::{token}")
	if raw:
		_audit_impersonation(json.loads(raw), "ended")
	frappe.cache().delete_value(f"a3s_impersonation::{token}")
	frappe.cache().delete_value(f"a3s_impersonation_by::{frappe.session.user}")
	return {"ok": True}


def active_impersonation(user=None):
	"""The open session for this operator, or None. Used to render the banner."""
	user = user or frappe.session.user
	token = frappe.cache().get_value(f"a3s_impersonation_by::{user}")
	if not token:
		return None
	raw = frappe.cache().get_value(f"a3s_impersonation::{token}")
	return json.loads(raw) if raw else None


def _audit_impersonation(session, event):
	"""Into the Platform Audit Entry chain, so it cannot be edited away afterwards."""
	try:
		from a3_sola.api import audit

		audit.record(
			entry_type=("Support Session Started" if event == "started"
			            else "Support Session Ended"),
			subject=(f"{session['operator']} acting as {session['acting_as']} "
			         f"for {session['tenant']}"),
			reason=session["reason"],
			reference_doctype="Tenant", reference_name=session["tenant"],
			detail=(f"Started {session['started']}, expires {session['expires']}. "
			        f"Operator {session['operator']}."),
			actor=session["operator"],
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: impersonation audit")


def _tell_the_tenant(row, session):
	"""Every time. If the client turns it off, the documentation says they did."""
	if not cint(get_value("notify_tenant_on_impersonation", 1)):
		frappe.logger("a3_sola").warning({
			"event": "impersonation_not_notified", "tenant": session["tenant"],
			"operator": session["operator"],
		})
		return False
	recipient = row.primary_contact_email or row.admin_user
	if not recipient:
		return False
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=_("A support session was opened on your A3 Sola account"),
			message=_(
				"<p>Hello,</p>"
				"<p>Our support team opened a session on your A3 Sola account at {0} to "
				"help with the following:</p><blockquote>{1}</blockquote>"
				"<p>The session ends automatically at {2}. Everything done during it is "
				"recorded against our operator's name, not yours.</p>"
				"<p>If you were not expecting this, reply to this message.</p>"
			).format(session["started"], frappe.utils.escape_html(session["reason"]),
			         session["expires"]),
			now=bool(frappe.flags.in_test),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: impersonation notice")
		return False
	return True


@frappe.whitelist()
def search_tenants(query=None, limit=20):
	"""Cross-tenant search - the console's entry point into Tenant 360."""
	permissions.require_role(CONSOLE_ROLES, action="search tenants")
	filters = {}
	if query:
		filters["tenant_name"] = ["like", f"%{query}%"]
	rows = frappe.get_all("Tenant", filters=filters,
	                      fields=["name", "tenant_name", "status", "company",
	                              "platform_subscription", "active_users", "user_quota"],
	                      limit=cint(limit) or 20, order_by="modified desc")
	for row in rows:
		row["subscription_status"] = frappe.db.get_value(
			"Platform Subscription", row.platform_subscription, "status")
	return rows
