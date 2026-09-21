# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What the quotation builder pages embed. Shared by the new and view pages, which live
in a folder Python cannot import from (its name carries a hyphen, as the URL does)."""

import json

import frappe

from a3_sola.api import cost_estimate, portal_chain


def seed_builder(context, record, lead="", prefill=None):
	"""Everything the builder script needs, as one JSON blob in the page."""
	data = {
		"catalogue": cost_estimate.catalogue(),
		"parties": cost_estimate.parties("Lead"),
		"record": record,
		"lead": lead,
		# Fields the chain carries across from the record this was opened from. The
		# builder seeds its own form with them; they are links and names, never prices.
		"prefill": prefill or {},
		"list_route": "/a3solaportal/quotations",
	}
	# `</` is escaped so no value inside can end the script block early.
	context.builder_json = json.dumps(data, default=str).replace("</", "<\\/")
	context.record = record
	context.mode = "view" if record and not record.get("editable") else ("edit" if record else "new")
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.back_link = {"href": "/a3solaportal/quotations", "label": "Back to quotations"}


def quotation_aside(context, name):
	"""Snapshot, at-a-glance and next-step context for one quotation.

	The builder is the quotation's detail page, so it carries the same three boxes as
	every other record in the chain rather than being the one page a person has to read
	differently. Built from the collections helpers, so a field added to the doctype shows
	up here without this module being touched.
	"""
	from a3_sola.www.a3solaportal.collections import (
		is_editable, record_glance, record_snapshot,
	)

	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("read")

	context.tiles = record_snapshot("quotations", doc)
	context.glance = record_glance(doc)
	context.chain_steps = portal_chain.steps_for(doc)
	context.record_doctype = doc.doctype
	context.record_name = doc.name
	context.can_write = is_editable(doc)
	context.submitted = frappe.utils.cint(doc.docstatus) == 1
	context.desk_route = "/app/quotation/{0}".format(frappe.utils.quote(doc.name))
	return context
