# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Step one again, for an estimate that exists: change its details, then back to step two."""

import frappe

from a3_sola.api import portal_estimate
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import load_record, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(portal_estimate.details_route(name) if name else "/a3solaportal/design-estimates")
	doc = load_record("design-estimates", name, "write")
	fill_shell(
		context,
		active_route="/a3solaportal/design-estimates",
		page_title="Details of " + doc.name,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Solar Design Estimate", "href": "/a3solaportal/design-estimates"},
			{"label": doc.name, "href": record_route("design-estimates", doc.name)},
			{"label": "Details"},
		],
	)
	context.record_name = doc.name
	context.columns = portal_estimate.detail_columns(doc)
	context.profile = portal_estimate.subject_profile(doc.lead, doc.solar_consumer)
	context.cancel_route = portal_estimate.design_route(doc.name)
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
