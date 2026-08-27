# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sales Order: the handoff into Solar Operations."""

import frappe

from a3_sola.api import handoff
from a3_sola.api.settings import get_value


def on_submit(doc, method=None):
	"""Advance the consumer and open the Solar Installation.

	Phase 2 lives in this same app, so this is a direct call. The feature flag remains only
	so a tenant running CRM alone can defer Operations; it is on by default.
	"""
	consumer = _solar_consumer_for(doc)
	if not consumer:
		return

	frappe.get_doc("Solar Consumer", consumer).set_status("Converted")
	if not doc.get("solar_consumer"):
		doc.db_set("solar_consumer", consumer, update_modified=False)

	if get_value("enable_phase2_handoff"):
		handoff.create_solar_installation(doc)


def _solar_consumer_for(doc):
	if doc.get("solar_consumer"):
		return doc.solar_consumer
	for item in doc.items:
		if item.prevdoc_docname:
			consumer = frappe.db.get_value("Quotation", item.prevdoc_docname, "solar_consumer")
			if consumer:
				return consumer
	return None
