# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The edit-a-lead form.

Login required, and write permission is checked before the form is rendered, so a user
who may only read a lead never sees a form that would fail on save. The form posts to
`a3_sola.api.leads.update_lead`; this page only renders the fields - from the same
`edit_fields` the endpoint uses as its allow-list - and hands the browser a CSRF token.

"""

import frappe

from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.api.leads import display_name, edit_fields, lead_route, lead_snapshot, load_lead

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(lead_route(name) + "/edit" if name else "/a3solaportal/leads")
	doc = load_lead(name, "write")
	title = display_name(doc)

	fill_shell(
		context,
		active_route="/a3solaportal/leads",
		page_title="Edit " + title,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Leads", "href": "/a3solaportal/leads"},
			{"label": title, "href": lead_route(doc.name)},
			{"label": "Edit"},
		],
	)

	context.lead = doc
	context.title = title
	context.sections = edit_fields(doc)
	context.view_route = lead_route(doc.name)
	context.back_link = {"href": context.view_route, "label": "Back to lead"}
	# The POST to the update endpoint is an unsafe method on an authenticated session, so
	# it needs a CSRF token. Generated here and read back from a meta tag by the form JS.
	context.csrf_token = frappe.sessions.get_csrf_token()

	# The About card: who this is and when the record last moved.
	snap = lead_snapshot(doc)
	context.about = snap["about"]
	context.created = snap["created"]
	context.modified = snap["modified"]
	return context
