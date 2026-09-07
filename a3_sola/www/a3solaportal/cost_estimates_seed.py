# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What the cost estimate builder pages embed. Shared by the new and view pages, which
live in a folder Python cannot import from (its name carries a hyphen, as the URL does)."""

import json

import frappe

from a3_sola.api import cost_estimate


def seed_builder(context, record, lead=""):
	"""Everything the builder script needs, as one JSON blob in the page."""
	data = {
		"catalogue": cost_estimate.catalogue(),
		"parties": cost_estimate.parties("Lead"),
		"record": record,
		"lead": lead,
		"list_route": "/a3solaportal/cost-estimates",
	}
	# `</` is escaped so no value inside can end the script block early.
	context.builder_json = json.dumps(data, default=str).replace("</", "<\\/")
	context.record = record
	context.mode = "view" if record and not record.get("editable") else ("edit" if record else "new")
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.back_link = {"href": "/a3solaportal/cost-estimates", "label": "Back to cost estimates"}
