# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One cost estimate: the same builder, loaded with the Quotation.

A draft the person may write is editable in place; anything submitted is shown read-only
with the way to ERPNext for amendment. The route `/a3solaportal/cost-estimates/<name>` is
mapped here by a website route rule in the platform registry.
"""

import frappe

from a3_sola.api import cost_estimate
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.cost_estimates_seed import seed_builder

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(cost_estimate.route_of(name) if name else "/a3solaportal/cost-estimates")
	if not name or not frappe.db.exists("Quotation", name):
		raise frappe.DoesNotExistError("That cost estimate does not exist.")
	record = cost_estimate.load(name)
	title = record["header"].get("title") or record["header"].get("customer_name") or name
	fill_shell(
		context,
		active_route="/a3solaportal/cost-estimates",
		page_title=title,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Cost Estimates", "href": "/a3solaportal/cost-estimates"},
			{"label": name},
		],
	)
	seed_builder(context, record=record)
	return context
