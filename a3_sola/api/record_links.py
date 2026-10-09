# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Lead, Solar Consumer and Site Survey: what one fills in the next, and how they point at
each other.

A consumer is made from a lead and a survey from a consumer, so whatever the earlier record
already knows - the DISCOM, the consumer number, the roof - arrives on the later one by
itself. The maps are the portal chain's (`portal_chain.CHAIN`), so a record created from
the lead's page, from the create form or from the desk is filled the same way.

The references run both ways: the consumer names its lead and the lead its consumer; the
survey names both, and the lead and the consumer each name their latest survey.
"""

import frappe
from frappe import _

from a3_sola.api import portal_chain

BLANK = (None, "", 0)


def _step(source_doctype, target_doctype):
	return next((s for s in portal_chain.steps_of(source_doctype) if s["doctype"] == target_doctype), None)


def values_from(source_doc, target_doctype):
	"""What the chain carries from `source_doc` onto a new `target_doctype`."""
	step = _step(source_doc.doctype, target_doctype)
	return portal_chain.mapped_values(step, source_doc) if step else {}


def fill_blanks(doc, values):
	"""Set each value on `doc` where the field is still empty.

	On a new record a Select still at its default counts as empty: nobody chose it, the
	form or the doctype did, and the earlier record knows better.
	"""
	for fieldname, value in values.items():
		df = doc.meta.get_field(fieldname)
		if not df or value in BLANK:
			continue
		current = doc.get(fieldname)
		untouched = doc.is_new() and df.fieldtype == "Select" and df.default and current == df.default
		if current in BLANK or untouched:
			doc.set(fieldname, value)


# ------------------------------------------------------------------ consumer
def fill_consumer(doc):
	"""A consumer is filled from its lead, wherever it is created."""
	if doc.lead and frappe.db.exists("Lead", doc.lead):
		fill_blanks(doc, values_from(frappe.get_doc("Lead", doc.lead), "Solar Consumer"))


def consumer_saved(doc):
	"""The lead names its consumer once it has one."""
	if doc.lead and not frappe.db.get_value("Lead", doc.lead, "solar_consumer"):
		frappe.db.set_value("Lead", doc.lead, "solar_consumer", doc.name, update_modified=False)


# ------------------------------------------------------------------ survey
def fill_survey(doc):
	"""A survey names both its lead and its consumer, each found from the other, and is
	filled from the consumer first and then the lead."""
	if doc.solar_consumer and not doc.lead:
		doc.lead = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "lead")
	if doc.lead and not doc.solar_consumer:
		doc.solar_consumer = frappe.db.get_value("Lead", doc.lead, "solar_consumer")
	if doc.lead and doc.solar_consumer:
		consumer_lead = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "lead")
		if consumer_lead and consumer_lead != doc.lead:
			frappe.throw(
				_("Solar Consumer {0} belongs to lead {1}, not {2}.").format(doc.solar_consumer, consumer_lead, doc.lead),
				title=_("Lead and Consumer Do Not Match"),
			)
	if doc.solar_consumer and frappe.db.exists("Solar Consumer", doc.solar_consumer):
		fill_blanks(doc, values_from(frappe.get_doc("Solar Consumer", doc.solar_consumer), "Site Survey"))
	if doc.lead and frappe.db.exists("Lead", doc.lead):
		lead = frappe.get_doc("Lead", doc.lead)
		fill_blanks(doc, {"company": lead.company, "roof_type": lead.get("roof_type")})


def latest_survey(consumer):
	"""The consumer's survey to point at: the newest submitted one, else the newest draft."""
	if not consumer:
		return None
	for docstatus in (1, 0):
		rows = frappe.get_all("Site Survey", filters={"solar_consumer": consumer, "docstatus": docstatus},
			pluck="name", order_by="creation desc", limit=1)
		if rows:
			return rows[0]
	return None


def sync_survey_refs(consumer, lead=None):
	"""Point the consumer and its lead at the consumer's latest survey."""
	if not consumer or not frappe.db.exists("Solar Consumer", consumer):
		return
	survey = latest_survey(consumer)
	frappe.db.set_value("Solar Consumer", consumer, "site_survey", survey, update_modified=False)
	lead = lead or frappe.db.get_value("Solar Consumer", consumer, "lead")
	if lead and frappe.db.exists("Lead", lead):
		frappe.db.set_value("Lead", lead, "site_survey", survey, update_modified=False)
		if not frappe.db.get_value("Lead", lead, "solar_consumer"):
			frappe.db.set_value("Lead", lead, "solar_consumer", consumer, update_modified=False)


def survey_changed(doc, method=None):
	sync_survey_refs(doc.solar_consumer, doc.lead)


# ------------------------------------------------------------------ create forms
@frappe.whitelist()
def prefill(doctype, lead=None, solar_consumer=None):
	"""What a create form fills in as the lead or consumer is chosen, read with the caller's
	own permissions. For a survey the lead brings its consumer and the consumer its lead."""
	if doctype not in ("Solar Consumer", "Site Survey"):
		frappe.throw(_("Nothing is filled in for {0}.").format(doctype))
	frappe.has_permission(doctype, "create", throw=True)
	out = {}
	if doctype == "Site Survey":
		if solar_consumer and not lead:
			lead = frappe.db.get_value("Solar Consumer", solar_consumer, "lead")
		if lead and not solar_consumer:
			solar_consumer = frappe.db.get_value("Lead", lead, "solar_consumer")
		if solar_consumer and frappe.has_permission("Solar Consumer", "read", solar_consumer):
			out.update(values_from(frappe.get_doc("Solar Consumer", solar_consumer), "Site Survey"))
		if lead and frappe.has_permission("Lead", "read", lead):
			lead_doc = frappe.get_doc("Lead", lead)
			for fieldname, value in (("lead", lead_doc.name), ("company", lead_doc.company), ("roof_type", lead_doc.get("roof_type"))):
				if value and not out.get(fieldname):
					out[fieldname] = value
		return out
	if lead and frappe.has_permission("Lead", "read", lead):
		out = values_from(frappe.get_doc("Lead", lead), "Solar Consumer")
	return out
