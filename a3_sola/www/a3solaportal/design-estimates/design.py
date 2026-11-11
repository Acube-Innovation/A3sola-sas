# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Step two of a design proposal: a tab per option of the design estimate, each its system and
commercials, then Compare, then the Proposal tab that makes the proposal of the saved options."""

import frappe

from a3_sola.api import portal_estimate, portal_proposal, portal_share
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import load_record, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(portal_estimate.design_route(name) if name else "/a3solaportal/design-estimates")
	doc = load_record("design-estimates", name, "read")
	fill_shell(
		context,
		active_route="/a3solaportal/proposals",
		page_title="Design " + doc.name,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Solar Design Proposal", "href": "/a3solaportal/proposals"},
			{"label": doc.name, "href": record_route("design-estimates", doc.name)},
			{"label": "Design"},
		],
	)
	# Three columns - sections, rows, commercials - so the page takes the full width.
	context.main_wide = True
	context.record_name = doc.name
	# The tabs are the options of the estimate this one was saved from, if any.
	# ?tab=proposal opens step three straight away (the proposal's Edit).
	context.builder_json = portal_estimate.page_json(doc, open_tab=(frappe.form_dict.get("tab") or "").strip())
	# Compare options goes to the customer as a PDF, with the share buttons of a proposal.
	root = portal_estimate.root_of(doc)
	context.compare_share = portal_share.share_links(root, portal_estimate.comparison_route(root.name), portal_share.COMPARISON)
	# The Proposal tab's form: the proposal's first page, who it is for shown from the estimate.
	context.proposal = portal_proposal.proposal_state(root)
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
