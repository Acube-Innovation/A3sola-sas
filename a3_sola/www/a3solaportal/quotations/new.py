# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The quotation builder, empty - or seeded with the record it was opened from.

Reached from the menu, or from the chain as `?source_dt=<doctype>&source=<name>`. A
Solar Proposal is the step that leads here, and a Lead is still accepted because the
builder has always taken `?lead=<name>`. The catalogue is embedded in the page so the
builder is usable the moment it paints, without a second round trip.
"""

import frappe

from a3_sola.api import portal_chain
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.quotations_seed import seed_builder

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/quotations/new")
	frappe.has_permission("Quotation", "create", throw=True)
	fill_shell(
		context,
		active_route="/a3solaportal/quotations",
		page_title="New quotation",
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Quotation", "href": "/a3solaportal/quotations"},
			{"label": "New"},
		],
	)
	source_dt = (frappe.form_dict.get("source_dt") or "").strip()
	source = (frappe.form_dict.get("source") or "").strip()

	lead = (frappe.form_dict.get("lead") or "").strip()
	if not lead and source_dt == "Lead":
		lead = source
	if lead and not frappe.db.exists("Lead", lead):
		lead = ""

	# Opened from the proposal it prices: the chain says which fields carry across, and
	# the source is read with the caller's own permissions.
	prefill = {}
	if source_dt and source and source_dt != "Lead":
		step = portal_chain.find_step(source_dt, "quotations")
		if step and frappe.db.exists(source_dt, source):
			source_doc = frappe.get_doc(source_dt, source)
			source_doc.check_permission("read")
			prefill = portal_chain.mapped_values(step, source_doc)
			# A Quotation names its party rather than its lead, so the lead the source
			# belongs to is passed separately for the builder to select.
			if not lead and source_doc.meta.get_field("lead") and source_doc.get("lead"):
				lead = source_doc.get("lead")
				if not frappe.db.exists("Lead", lead):
					lead = ""

	seed_builder(context, record=None, lead=lead, prefill=prefill)
	return context
