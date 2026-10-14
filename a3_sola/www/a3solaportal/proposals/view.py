# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one proposal, with its version history.

A proposal is the one document on the chain that goes out, comes back and goes out again,
so its page is the generic record view plus the history of that: what each version quoted,
how it was sent, and what the customer said. The actions that write that history are the
same whitelisted endpoints the desk calls.
"""

import frappe
from frappe.utils import flt, format_datetime, fmt_money

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
	# A proposal goes on after it is submitted: edited into a new version, regenerated,
	# dispatched. Only a cancelled one - replaced by its amendment - is closed.
	context.can_write = bool(doc.has_permission("write")) and frappe.utils.cint(doc.docstatus) < 2
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
	# The current version went to the client: Next steps offers Revise, not Regenerate.
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import version_choices, version_is_out

	current = doc.versions[-1] if doc.versions else None
	context.version_out = version_is_out(current)
	context.current_version_no = current.version_no if current else 0
	# Create quotation asks which version the client chose; Revise, which estimate the new
	# version quotes. Handed to portal_proposal.js as JSON.
	context.proposal_choices = {
		"versions": version_choices(doc),
		"estimates": estimate_choices(doc),
		"base": doc.solar_design_estimate or "",
	}
	context.is_accepted = doc.status == "Accepted"
	context.quotation = frappe.db.get_value(
		"Quotation", {"solar_proposal": doc.name, "docstatus": ["<", 2]}, "name"
	)
	# The chain's plain Create quotation would skip asking which version the client chose:
	# Next steps offers its own (portal_proposal_next.html) until the quotation exists, and
	# then the chain's card for it.
	context.chain_steps = [step for step in context.chain_steps or []
		if step.get("key") != "quotation" or step.get("done")]
	context.can_quote = bool(not context.quotation and context.versions
		and frappe.has_permission("Quotation", "create"))
	# The version history, then the Design Comparison of the proposal's estimates.
	context.extra_template = "templates/includes/portal_proposal_extra.html"
	from a3_sola.api.proposal import proposal_estimate_names
	from a3_sola.api.proposal_comparison import render as render_comparison

	context.comparison_html = render_comparison(proposal_estimate_names(doc))
	# Generate / Regenerate sits in Next steps, above Create quotation; the PDF and its
	# sharing beside Edit.
	context.chain_lead_template = "templates/includes/portal_proposal_next.html"
	context.head_actions_template = "templates/includes/portal_share.html"
	from urllib.parse import quote

	from a3_sola.api.portal_share import share_links

	context.share = share_links(doc, "/api/method/a3_sola.api.portal_proposal.pdf?name=" + quote(doc.name))
	# The actions below are unsafe methods on an authenticated session, so they need a token.
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


def estimate_choices(doc):
	"""The customer's design estimates a new version can quote, newest first."""
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import lead_estimates

	names = list(dict.fromkeys(lead_estimates(doc.lead, doc.solar_consumer)
		+ [r.solar_design_estimate for r in doc.get("design_estimates") or [] if r.solar_design_estimate]))
	rows = frappe.get_all("Solar Design Estimate", filters={"name": ["in", names], "docstatus": ["<", 2]},
		fields=["name", "solar_package", "final_capacity_kw", "modified"], order_by="creation desc")
	out = []
	for row in rows:
		package = frappe.db.get_value("Solar Package", row.solar_package, "package_name") if row.solar_package else ""
		out.append({"value": row.name, "label": " \u00b7 ".join(p for p in (
			row.name, package, "{0:g} kW".format(flt(row.final_capacity_kw)),
			"changed " + format_datetime(row.modified, "d MMM, h:mm a")) if p)})
	return out
