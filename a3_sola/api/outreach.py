# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The WhatsApp/email outreach cadence, message rendering and the follow-up scheduler.

This replaces the client's lead-tracker spreadsheet. Three dimensions are tracked
separately and must not be collapsed into one status field, because a lead can be at
step 3 of the cadence while the last call went unanswered - and that combination is
exactly what the sales manager needs to see.
"""

import urllib.parse

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today

from a3_sola.api.settings import get_int, get_settings

CADENCE_ORDER = [
	"Step 1: First Contact",
	"Step 2: 24hr Nudge",
	"Step 3: Value/ROI",
	"Step 4: Breakup/Close",
	"Completed: Proposal Sent",
]
TERMINAL_LEAD_STATUS = ("Converted / Won", "Closed / Unresponsive", "Not Interested")


def get_cadence():
	"""The configured cadence steps, in order."""
	settings = get_settings()
	steps = {row.step_name: row for row in settings.outreach_cadence}
	return [steps[name] for name in CADENCE_ORDER if name in steps]


def next_step(current):
	"""The step that follows `current`, or None at the end of the cadence."""
	try:
		idx = CADENCE_ORDER.index(current)
	except ValueError:
		return CADENCE_ORDER[0]
	return CADENCE_ORDER[idx + 1] if idx + 1 < len(CADENCE_ORDER) else None


def step_offset_days(step_name):
	for row in get_cadence():
		if row.step_name == step_name:
			return int(row.offset_days_from_previous or 0)
	return 0


def signature_block():
	"""Signature plus social links, assembled from Settings.

	Held as data so a second tenant is not publishing the first tenant's Instagram.
	"""
	settings = get_settings()
	parts = []
	if settings.outreach_signature:
		parts.append(settings.outreach_signature.strip())
	if settings.brand_website:
		parts.append(f"Web: {settings.brand_website}")
	links = [row for row in settings.brand_social_links if row.show_in_message]
	links.sort(key=lambda r: (r.display_order or 0, r.link_label or ""))
	parts.extend(f"- {row.link_label}: {row.link_url}" for row in links)
	return "\n".join(parts)


@frappe.whitelist()
def render_message(template, doc=None, context=None):
	"""Render an Outreach Message Template for a document.

	WhatsApp bold markers (*) are preserved verbatim - never convert them to HTML, or the
	message pastes wrongly into WhatsApp.
	"""
	tpl = frappe.get_cached_doc("Outreach Message Template", template)
	ctx = dict(context or {})
	if doc is not None:
		if isinstance(doc, str):
			doc = frappe.get_doc(frappe.flags.outreach_doctype or "Lead", doc)
		ctx.setdefault("doc", doc)
		ctx.setdefault("first_name", (getattr(doc, "lead_name", None) or getattr(doc, "customer_name", "") or "").split(" ")[0])
		ctx.setdefault("full_name", getattr(doc, "lead_name", None) or getattr(doc, "customer_name", ""))
	ctx.setdefault("settings", get_settings())

	body = frappe.render_template(tpl.message_body or "", ctx)
	tail = []
	if tpl.include_signature or tpl.include_social_links:
		block = signature_block()
		if block:
			tail.append(block)
	return "\n\n".join([body.strip(), *tail]).strip()


@frappe.whitelist()
def whatsapp_link(mobile_no, message):
	"""A wa.me deep link prefilled with the rendered text.

	Deliberately not an API send: the client messages from a personal number and the
	business-API decision has not been taken. This puts the message one tap away without
	pretending to send on their behalf.
	"""
	digits = "".join(ch for ch in (mobile_no or "") if ch.isdigit())
	if digits and not digits.startswith("91") and len(digits) == 10:
		digits = "91" + digits
	return f"https://wa.me/{digits}?text={urllib.parse.quote(message or '')}"


@frappe.whitelist()
def log_outreach(lead, channel, outreach_step=None, call_status=None, outcome=None, next_action=None, message_template=None):
	"""Append an Outreach Log row and advance the cadence.

	The single most-used action in the app, so it is one call and two taps on a phone.
	"""
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	doc.append(
		"outreach_log",
		{
			"contact_datetime": now_datetime(),
			"channel": channel,
			"outreach_step": outreach_step or doc.outreach_stage or CADENCE_ORDER[0],
			"call_status": call_status,
			"outcome": outcome,
			"next_action": next_action,
			"message_template": message_template,
			"logged_by": frappe.session.user,
		},
	)
	apply_outreach_state(doc)
	doc.save(ignore_permissions=True)
	return {
		"outreach_stage": doc.outreach_stage,
		"next_followup_date": doc.next_followup_date,
		"followup_status": doc.followup_status,
		"consecutive_non_connects": doc.consecutive_non_connects,
	}


def apply_outreach_state(doc):
	"""Recompute the outreach fields on a Lead from its log. Never hand-set."""
	rows = sorted(doc.get("outreach_log") or [], key=lambda r: str(r.contact_datetime or ""))
	if not rows:
		compute_followup_status(doc)
		return

	last = rows[-1]
	if last.call_status:
		doc.call_status = last.call_status
	doc.last_message_date = getdate(last.contact_datetime)

	streak = 0
	for row in reversed(rows):
		if row.call_status in ("Not Answered", "Busy", "Switched Off"):
			streak += 1
		elif row.call_status == "Connected":
			break
	doc.consecutive_non_connects = streak

	if last.outreach_step and last.outreach_step != "Ad-hoc":
		doc.outreach_stage = last.outreach_step

	following = next_step(doc.outreach_stage)
	if following:
		doc.next_followup_date = add_days(getdate(last.contact_datetime), step_offset_days(following) or 1)
	elif doc.outreach_stage == "Completed: Proposal Sent":
		doc.next_followup_date = add_days(getdate(last.contact_datetime), 3)

	compute_followup_status(doc)


def compute_followup_status(doc):
	"""FOLLOW UP DUE is computed, never editable. Due leads are the first dashboard number."""
	if (doc.get("solar_lead_status") or "") in TERMINAL_LEAD_STATUS:
		doc.followup_status = "OK"
		return
	grace = get_int("followup_overdue_grace_days", 0)
	if doc.next_followup_date and getdate(doc.next_followup_date) <= getdate(add_days(today(), grace)):
		doc.followup_status = "FOLLOW UP DUE"
	else:
		doc.followup_status = "OK"


def daily_followup_scan():
	"""Daily scheduler: recompute follow-up status per company and notify owners once.

	Iterates companies explicitly and never issues an unfiltered query.
	"""
	if not frappe.db.get_single_value("A3 Sola Settings", "enable_followup_automation"):
		return

	summary = {}
	for company in frappe.get_all("Company", pluck="name"):
		leads = frappe.get_all(
			"Lead",
			filters={
				"company": company,
				"status": ["not in", ["Converted", "Do Not Contact"]],
				"next_followup_date": ["is", "set"],
			},
			fields=["name", "lead_name", "owner", "next_followup_date", "followup_status", "solar_lead_status"],
		)
		due_by_owner = {}
		for lead in leads:
			doc = frappe.get_doc("Lead", lead.name)
			before = doc.followup_status
			compute_followup_status(doc)
			if doc.followup_status != before:
				frappe.db.set_value("Lead", doc.name, "followup_status", doc.followup_status, update_modified=False)
			if doc.followup_status == "FOLLOW UP DUE":
				due_by_owner.setdefault(lead.owner, []).append(lead)

		for owner, rows in due_by_owner.items():
			_notify_owner(owner, rows, company)
		summary[company] = sum(len(v) for v in due_by_owner.values())

	frappe.logger("a3_sola").info(f"daily_followup_scan: {summary}")
	return summary


def _notify_owner(owner, rows, company):
	"""One ToDo per owner per day, not one per lead."""
	description = _("{0} solar leads are due for follow-up in {1}: {2}").format(
		len(rows), company, ", ".join(r.lead_name or r.name for r in rows[:10])
	)
	existing = frappe.db.exists(
		"ToDo",
		{
			"allocated_to": owner,
			"reference_type": "Lead",
			"status": "Open",
			"date": today(),
			"description": ["like", "%due for follow-up%"],
		},
	)
	if existing:
		return
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": owner,
			"date": today(),
			"priority": "Medium",
			"description": description,
			"reference_type": "Lead",
			"reference_name": rows[0].name,
		}
	).insert(ignore_permissions=True)
