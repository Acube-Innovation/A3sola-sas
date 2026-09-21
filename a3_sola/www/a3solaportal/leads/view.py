# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One lead, read from ERPNext and laid out for a person rather than a form.

Login required. The record is loaded with `frappe.get_doc` and read-checked, so a user
sees a lead only if the desk would show it to them. The route carries the lead's name -
`/a3solaportal/leads/<name>` is mapped here by a website route rule in the platform
registry - and an unknown name is a 404, not an empty page.

The page mirrors the edit page: the sections as long cards down the left, and on the
right the same snapshot and at-a-glance summary, so a person moving between the two
never has to re-find anything.
"""

import frappe
from frappe.utils import format_datetime, strip_html

from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.api import assignments, portal_chain
from a3_sola.api.leads import (
	detail_sections, display_name, glance_rows, lead_route, lead_snapshot, load_lead,
)

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(lead_route(name) if name else "/a3solaportal/leads")
	doc = load_lead(name)
	title = display_name(doc)

	fill_shell(
		context,
		active_route="/a3solaportal/leads",
		page_title=title,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Leads", "href": "/a3solaportal/leads"},
			{"label": title},
		],
	)

	context.lead = doc
	context.title = title
	context.status_slug = (doc.status or "").lower().replace(" ", "-")
	context.subline = [
		v for v in (
			doc.company_name if doc.company_name != title else None,
			doc.email_id,
			doc.mobile_no,
		) if v
	]
	context.sections = detail_sections(doc)

	# How much of the record is filled in, for the snapshot tile.
	rows = [r for s in context.sections for r in s["rows"]]
	filled = len([r for r in rows if r["kind"] != "empty"])
	context.filled = filled
	context.total = len(rows)
	context.filled_pct = int(round(filled * 100 / len(rows))) if rows else 0

	# Latest contact first: the question is "what happened last", not "what happened first".
	context.outreach_log = [
		{
			"when": format_datetime(row.contact_datetime, "medium") if row.contact_datetime else "",
			"channel": row.channel or "",
			"step": row.outreach_step or "",
			"call_status": row.call_status or "",
			"outcome": row.outcome or "",
			"next_action": row.next_action or "",
			"logged_by": row.logged_by or "",
		}
		for row in reversed(doc.get("outreach_log") or [])
	]
	# CRM notes are rich text on the desk; here they are plain text, so nothing a note
	# contains can run in the portal.
	context.notes = [
		{
			"text": strip_html(row.note or "").strip(),
			"by": row.added_by or "",
			"on": format_datetime(row.added_on, "medium") if row.added_on else "",
		}
		for row in reversed(doc.get("notes") or [])
		if (row.note or "").strip()
	]

	context.snapshot = lead_snapshot(doc)
	context.about = context.snapshot["about"]
	context.created = context.snapshot["created"]
	context.modified = context.snapshot["modified"]
	context.glance = glance_rows(doc)

	context.can_write = doc.has_permission("write")
	context.edit_route = lead_route(doc.name) + "/edit"
	context.back_link = {"href": "/a3solaportal/leads", "label": "Back to leads"}
	context.chain_steps = portal_chain.steps_for(doc)
	context.record_doctype = doc.doctype
	context.record_name = doc.name
	context.assignees = assignments.assignees(doc.doctype, doc.name)
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
