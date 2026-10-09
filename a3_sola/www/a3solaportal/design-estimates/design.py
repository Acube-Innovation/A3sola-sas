# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Step two of a design estimate: the system, one table at a time, priced alongside."""

import frappe

from a3_sola.api import portal_estimate
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import load_record, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(portal_estimate.design_route(name) if name else "/a3solaportal/design-estimates")
	doc = load_record("design-estimates", name, "read")
	fill_shell(
		context,
		active_route="/a3solaportal/design-estimates",
		page_title="Design " + doc.name,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Solar Design Estimate", "href": "/a3solaportal/design-estimates"},
			{"label": doc.name, "href": record_route("design-estimates", doc.name)},
			{"label": "Design"},
		],
	)
	# Three columns - sections, rows, commercials - so the page takes the full width.
	context.main_wide = True
	context.record_name = doc.name
	context.builder_json = portal_estimate.builder_json(doc)
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
