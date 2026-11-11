# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Step one of a new design proposal: the design estimate's details, in two columns. Next creates
the estimate and goes on to its options; the proposal itself is made on the last step."""

import frappe

from a3_sola.api import portal_chain, portal_estimate
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/design-estimates/new")
	frappe.has_permission("Solar Design Estimate", "create", throw=True)
	fill_shell(
		context,
		active_route="/a3solaportal/proposals",
		page_title="New design proposal",
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Solar Design Proposal", "href": "/a3solaportal/proposals"},
			{"label": "New"},
		],
	)
	context.record_name = ""
	# Opened from a lead, consumer or survey: what it says carries across, and the rest
	# of the chain (consumer, lead, tariff, phase) is read from it.
	prefill = {}
	source_dt = (frappe.form_dict.get("source_dt") or "").strip()
	source = (frappe.form_dict.get("source") or "").strip()
	if source_dt == "Lead":
		prefill = {"lead": source}
	elif source_dt and source:
		step = portal_chain.find_step(source_dt, portal_estimate.SLUG)
		if step and frappe.db.exists(source_dt, source) and frappe.has_permission(source_dt, "read", source):
			prefill = portal_chain.mapped_values(step, frappe.get_doc(source_dt, source))
	prefill = portal_estimate.estimate_prefill(prefill)
	context.columns = portal_estimate.detail_columns(prefill=prefill)
	context.packages_json = portal_estimate.package_choices_json(context.columns)
	context.profile = portal_estimate.subject_profile(prefill.get("lead"), prefill.get("solar_consumer"))
	context.cancel_route = "/a3solaportal/proposals"
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
