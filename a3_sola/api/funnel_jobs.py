# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Scheduled housekeeping for the funnel.

Three jobs, all idempotent, all logged:

* Chase then abandon signups that never verified.
* Purge personal data and spent tokens once they have served their purpose. This is a
  data-minimisation measure and it is ON by default - holding somebody's IP address
  indefinitely because nobody configured a retention period is not a defensible position.
* Email sales a weekly funnel summary.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, now_datetime, today

from a3_sola.api import platform
from a3_sola.api.settings import get_int, get_value

PENDING = ("Draft", "Awaiting Email Verification")


def chase_and_abandon_signups():
	"""Daily: one reminder, then abandonment. Never more than one reminder per signup."""
	reminder_hours = get_int("signup_reminder_after_hours", 24) or 24
	abandon_days = get_int("signup_abandon_after_days", 7) or 7

	reminded = abandoned = 0
	rows = frappe.get_all(
		"Subscription Signup",
		filters={"status": ["in", PENDING], "is_email_verified": 0, "docstatus": ["<", 2]},
		fields=["name", "creation"],
		limit_page_length=0,
	)
	for row in rows:
		age_hours = frappe.utils.time_diff_in_hours(now_datetime(), row.creation)
		if age_hours >= abandon_days * 24:
			if _abandon(row.name, abandon_days):
				abandoned += 1
		elif age_hours >= reminder_hours:
			if _remind_once(row.name):
				reminded += 1

	frappe.logger("a3_sola").info(
		{"event": "signup_chase", "reminded": reminded, "abandoned": abandoned}
	)
	return {"reminded": reminded, "abandoned": abandoned}


def _remind_once(name):
	doc = frappe.get_doc("Subscription Signup", name)
	# One reminder, ever. A funnel that nags is a funnel people report as spam.
	if any(row.event_type == "Verification Resent" for row in doc.event_log):
		return False
	try:
		from a3_sola.api.signup import _issue_verification

		_issue_verification(doc, resend=True)
		return True
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: reminder for {name}")
		return False


def _abandon(name, days):
	doc = frappe.get_doc("Subscription Signup", name)
	doc.set_status(
		"Abandoned",
		reason=_("Email never verified within {0} days.").format(days),
		details=_("Marked abandoned by the daily job."),
	)
	# The token is dead the moment the signup is: leaving a live one on an abandoned
	# record is a link somebody could still walk into months later.
	doc.verification_token = None
	doc.token_expires_on = None
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	return True


def purge_personal_data():
	"""Daily: drop what we no longer need.

	Two separate retention periods, because they protect different things. The token is a
	credential; the IP and user agent are personal data kept only to investigate abuse.
	"""
	token_days = get_int("verification_token_retention_days", 30) or 30
	personal_days = get_int("personal_data_retention_days", 30) or 30

	tokens = frappe.db.sql(
		"""
		update `tabSubscription Signup`
		set verification_token = null, token_expires_on = null
		where verification_token is not null and creation < %s
		""",
		(add_days(today(), -token_days),),
	)

	purged = 0
	for doctype in ("Subscription Signup", "Demo Request"):
		purged += frappe.db.sql(
			f"""
			update `tab{doctype}`
			set ip_address = null, user_agent = null
			where (ip_address is not null or user_agent is not null) and creation < %s
			""",
			(add_days(today(), -personal_days),),
		) or 0

	frappe.db.commit()
	frappe.logger("a3_sola").info(
		{"event": "funnel_data_purge", "token_days": token_days, "personal_days": personal_days}
	)
	return {"tokens_cleared": bool(tokens), "records_purged": purged}


def weekly_funnel_summary():
	"""Weekly: what the funnel did, to whoever answers sales@."""
	recipient = get_value("sales_email")
	if not recipient:
		return None

	since = add_days(today(), -7)
	signups = frappe.get_all(
		"Subscription Signup",
		filters={"creation": [">=", since], "docstatus": ["<", 2]},
		fields=["status", "plan_code", "billing_cycle", "total_amount", "is_email_verified"],
		limit_page_length=0,
	)
	demos = frappe.db.count("Demo Request", {"creation": [">=", since]})
	verified = len([s for s in signups if s.is_email_verified])
	paid = len([s for s in signups if s.status in ("Paid", "Provisioning", "Active")])
	value = sum(frappe.utils.flt(s.total_amount) for s in signups)

	summary = {
		"since": since,
		"signups": len(signups),
		"verified": verified,
		"paid": paid,
		"demos": demos,
		"value": value,
		"verification_rate": round(verified * 100.0 / len(signups), 1) if signups else 0,
	}
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=_("Funnel summary: {0} signups, {1} demo requests").format(
				summary["signups"], demos
			),
			message=frappe.render_template(
				"a3_sola/templates/emails/weekly_funnel.html",
				platform.email_context({"summary": summary}),
			),
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: weekly funnel summary")
	frappe.logger("a3_sola").info({"event": "weekly_funnel_summary", **summary})
	return summary
