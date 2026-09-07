# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one proposal, with its version history.

A proposal is the one document on the chain that goes out, comes back and goes out again,
so its page is the generic record view plus the history of that: what each version quoted,
how it was sent, and what the customer said. The actions that write that history are the
same whitelisted endpoints the desk calls.
"""

import frappe
from frappe.utils import format_datetime, fmt_money

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route

no_cache = 1

#: Tone for each outcome, so the history reads at a glance.
OUTCOME_TONE = {
	"Accepted": "green",
	"Revision Requested": "amber",
	"Rejected": "red",
	"Lost": "red",
	"Awaiting Response": "muted",
}


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("proposals", name) if name else "/a3solaportal/proposals")
	detail_context(context, "proposals", name)

	doc = context.record
	# Newest first: the question on this page is what happened last.
	context.versions = [
		{
			"version_no": v.version_no,
			"raised": format_datetime(v.version_date, "medium") if v.version_date else "",
			"estimate": v.solar_design_estimate,
			"capacity": v.capacity_label or "",
			"cost": fmt_money(v.recommended_option_cost) if v.recommended_option_cost else "",
			"pdf": v.proposal_pdf,
			"file_name": v.proposal_file_name or "",
			"sent_via": v.sent_via or "Not Sent",
			"sent_on": format_datetime(v.sent_on, "medium") if v.sent_on else "",
			"sent_by": v.sent_by or "",
			"outcome": v.outcome or "Awaiting Response",
			"tone": OUTCOME_TONE.get(v.outcome or "Awaiting Response", "muted"),
			"responded_on": format_datetime(v.responded_on, "medium") if v.responded_on else "",
			"client_comments": v.client_comments or "",
			"lost_reason": v.lost_reason or "",
			"notes": v.notes or "",
			"is_current": v.version_no == doc.current_version,
		}
		for v in reversed(doc.versions or [])
	]
	context.has_versions = bool(context.versions)
	context.is_accepted = doc.status == "Accepted"
	context.quotation = frappe.db.get_value(
		"Quotation", {"solar_proposal": doc.name, "docstatus": ["<", 2]}, "name"
	)
	context.extra_template = "templates/includes/portal_proposal_versions.html"
	# The actions below are unsafe methods on an authenticated session, so they need a token.
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
