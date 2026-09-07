# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The cost estimate builder, empty - or seeded with the lead it was opened from.

Reached from the menu, or from a lead's page with `?lead=<name>` (the chain's
`?source_dt=Lead&source=<name>` is accepted too). The catalogue is embedded in the page
so the builder is usable the moment it paints, without a second round trip.
"""

import frappe

from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.cost_estimates_seed import seed_builder

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/cost-estimates/new")
	frappe.has_permission("Quotation", "create", throw=True)
	fill_shell(
		context,
		active_route="/a3solaportal/cost-estimates",
		page_title="New cost estimate",
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Cost Estimates", "href": "/a3solaportal/cost-estimates"},
			{"label": "New"},
		],
	)
	lead = (frappe.form_dict.get("lead") or "").strip()
	if not lead and (frappe.form_dict.get("source_dt") or "") == "Lead":
		lead = (frappe.form_dict.get("source") or "").strip()
	if lead and not frappe.db.exists("Lead", lead):
		lead = ""
	seed_builder(context, record=None, lead=lead)
	return context
