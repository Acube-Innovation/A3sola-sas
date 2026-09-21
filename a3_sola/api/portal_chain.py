# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The next step from one record to the next, along the solar chain.

A lead becomes a consumer; a consumer gets a proposal. The portal shows that as one
button per step on the record's own page, which turns into a card once the step is done.
This module holds the whole declaration - what may be created from what, which fields
carry across, and where the link between the two records lives - so a page renders the
chain without knowing anything about the doctypes in it.

Nothing here writes. `a3_sola.api.portal_crud.create_record` does the write and asks this
module what to carry across; the pages ask it what to show.
"""

import frappe
from frappe import _

# The chain is linear: Lead > Solar Consumer > Site Survey > Solar Design Estimate >
# Subsidy Eligibility Check > Solar Proposal > Quotation > Sales Order. Each source
# doctype therefore declares exactly one step - the record made next from it - so a page
# offers one thing to do and the sequence cannot be taken out of order.
#
#   slug/doctype   where the step leads
#   link_field     the field ON THE SOURCE that points at the target, when there is one.
#                  Its absence means the link lives on the target instead, and the target
#                  is found by searching for it.
#   child_link     where the target records the source in a child table instead of a
#                  field of its own, as ERPNext's Sales Order Item does for a Quotation.
#   via            a dotted path to an ERPNext mapper. Its presence means the step is a
#                  POST that builds the whole document, not a create form.
#   needs_submit   the source must be submitted before the step is offered.
#   map            target fieldname -> source fieldname, or a tuple of source fieldnames
#                  meaning "the first of these that has a value"
#   defaults       target fieldname -> a literal, used only when the map produced nothing
#   card_*         what the card shows once the step is done
CHAIN = {
	"Lead": [
		{
			"key": "consumer",
			"slug": "consumers",
			"doctype": "Solar Consumer",
			"label": "Create solar consumer",
			"icon": "user",
			"link_field": "solar_consumer",
			"card_title": "consumer_name",
			"card_subtitle": "consumer_number",
			"card_subtitle_label": "Consumer no.",
			"map": {
				"consumer_name": ("lead_name", "company_name"),
				"mobile_no": ("mobile_no", "phone"),
				"email_id": "email_id",
				"consumer_category": "consumer_category",
				"discom": "discom",
				"discom_section": "discom_section",
				"consumer_number": "consumer_number",
				"connection_type": "connection_type",
				"roof_type": "roof_type",
				"avg_consumption_units": "approx_consumption_units",
				"avg_bill_amount": "avg_monthly_bill",
				"company": "company",
				"lead": "name",
			},
			"defaults": {"consumer_category": "Residential", "billing_frequency": "Bimonthly"},
		},
	],
	"Solar Consumer": [
		{
			"key": "survey",
			"slug": "site-surveys",
			"doctype": "Site Survey",
			"label": "Create site survey",
			"icon": "pin",
			"card_title": "name",
			"card_subtitle": "feasibility_status",
			"card_subtitle_label": "Feasibility",
			"map": {
				"solar_consumer": "name",
				"customer_name": "consumer_name",
				"discom": "discom",
				"discom_section": "discom_section",
				"roof_type": "roof_type",
				"company": "company",
			},
		},
		# The consumer is the one record the whole job hangs off, so its page offers the
		# three documents that name it directly as well as the survey that follows it.
		# Everywhere else the chain stays linear; here a person picks up wherever the job
		# actually is, which is not always the next step in the sequence.
		{
			"key": "estimate",
			"slug": "design-estimates",
			"doctype": "Solar Design Estimate",
			"label": "Create solar design estimate",
			"icon": "pen",
			"card_title": "name",
			"card_subtitle": "binding_constraint",
			"card_subtitle_label": "Sized by",
			"map": {
				"solar_consumer": "name",
				"lead": "lead",
				"connection_type": "connection_type",
				"company": "company",
			},
		},
		{
			"key": "eligibility",
			"slug": "subsidy-eligibility",
			"doctype": "Subsidy Eligibility Check",
			"label": "Create subsidy eligibility check",
			"icon": "check",
			"card_title": "name",
			"card_subtitle": "overall_result",
			"card_subtitle_label": "Result",
			"map": {
				"solar_consumer": "name",
				"lead": "lead",
				"consumer_name": "consumer_name",
				"mobile_no": "mobile_no",
				"email_id": "email_id",
				"consumer_category": "consumer_category",
				"connection_type": "connection_type",
				"discom": "discom",
				"discom_section": "discom_section",
				"consumer_number": "consumer_number",
				"roof_type": "roof_type",
				"avg_bill_amount": "avg_bill_amount",
				"company": "company",
			},
		},
		{
			"key": "proposal",
			"slug": "proposals",
			"doctype": "Solar Proposal",
			"label": "Create solar proposal",
			"icon": "doc",
			# A proposal quotes a design estimate - the field is mandatory on it - so the
			# step is shown but held until there is one to quote.
			"requires": "estimate",
			"requires_note": "A proposal quotes a design estimate, so make that first.",
			"card_title": "name",
			"card_subtitle": "status",
			"card_subtitle_label": "Status",
			"map": {
				"solar_consumer": "name",
				"lead": "lead",
				"customer_name": "consumer_name",
				"mobile_no": "mobile_no",
				"email_id": "email_id",
				"location": ("village", "local_body_name"),
				"company": "company",
			},
		},
	],
	"Site Survey": [
		{
			"key": "estimate",
			"slug": "design-estimates",
			"doctype": "Solar Design Estimate",
			"label": "Create solar design estimate",
			"icon": "pen",
			"card_title": "name",
			"card_subtitle": "binding_constraint",
			"card_subtitle_label": "Sized by",
			"map": {
				"site_survey": "name",
				"solar_consumer": "solar_consumer",
				"company": "company",
			},
		},
	],
	"Solar Design Estimate": [
		{
			"key": "eligibility",
			"slug": "subsidy-eligibility",
			"doctype": "Subsidy Eligibility Check",
			"label": "Create subsidy eligibility check",
			"icon": "check",
			"card_title": "name",
			"card_subtitle": "overall_result",
			"card_subtitle_label": "Result",
			"map": {
				"design_estimate": "name",
				"solar_consumer": "solar_consumer",
				"lead": "lead",
				"subsidy_scheme": "subsidy_scheme",
				"capacity_kw": "final_capacity_kw",
				"company": "company",
			},
		},
	],
	"Subsidy Eligibility Check": [
		{
			"key": "proposal",
			"slug": "proposals",
			"doctype": "Solar Proposal",
			"label": "Create solar proposal",
			"icon": "doc",
			"card_title": "name",
			"card_subtitle": "status",
			"card_subtitle_label": "Status",
			"map": {
				"solar_design_estimate": "design_estimate",
				"solar_consumer": "solar_consumer",
				"lead": "lead",
				"customer_name": "consumer_name",
				"mobile_no": "mobile_no",
				"company": "company",
			},
		},
	],
	"Solar Proposal": [
		{
			"key": "quotation",
			"slug": "quotations",
			"doctype": "Quotation",
			"label": "Create quotation",
			"icon": "calc",
			"card_title": "name",
			"card_subtitle": "status",
			"card_subtitle_label": "Status",
			"map": {
				"solar_proposal": "name",
				"solar_consumer": "solar_consumer",
				"solar_design_estimate": "solar_design_estimate",
				"company": "company",
			},
		},
	],
	"Quotation": [
		{
			"key": "sales-order",
			"slug": "sales-orders",
			"doctype": "Sales Order",
			"label": "Create sales order",
			"icon": "cart",
			# ERPNext already knows how to turn a quotation into an order, items, taxes
			# and all. Re-deriving that here would be a second, worse implementation of it.
			"via": "erpnext.selling.doctype.quotation.quotation.make_sales_order",
			"needs_submit": True,
			"needs_submit_note": "A sales order is raised from a submitted quotation, so submit this one first.",
			"child_link": {"doctype": "Sales Order Item", "field": "prevdoc_docname"},
			"card_title": "name",
			"card_subtitle": "status",
			"card_subtitle_label": "Status",
		},
	],
}


def steps_of(doctype):
	return CHAIN.get(doctype, [])


def find_step(source_doctype, slug):
	"""The step leading from `source_doctype` to `slug`, or None.

	Called before any create-from write, so an unknown pairing is simply refused rather
	than being treated as a create with attacker-chosen field values.
	"""
	for step in steps_of(source_doctype):
		if step["slug"] == slug:
			return step
	return None


def _backlink_field(step, source_doctype):
	"""The Link field on the target that points back at the source, if any."""
	for df in frappe.get_meta(step["doctype"]).get_link_fields():
		if df.options == source_doctype:
			return df.fieldname
	return None


def find_target(step, doc):
	"""The record this step already produced, or None.

	Two ways round, because the link lives on whichever side the doctypes put it: a Lead
	names its consumer, while a proposal names the consumer it belongs to.
	"""
	link_field = step.get("link_field")
	if link_field and doc.meta.get_field(link_field):
		name = doc.get(link_field)
		if name and frappe.db.exists(step["doctype"], name):
			return name
		if name:
			return None

	child = step.get("child_link")
	if child:
		# ERPNext records a quotation on the order's item rows, not on the order itself.
		try:
			found = frappe.get_all(
				child["doctype"], filters={child["field"]: doc.name, "docstatus": ["<", 2]},
				pluck="parent", order_by="creation desc", limit_page_length=1,
			)
		except frappe.PermissionError:
			return None
		if found and frappe.db.exists(step["doctype"], found[0]):
			return found[0]
		return None

	field = _backlink_field(step, doc.doctype)
	if not field:
		return None
	try:
		found = frappe.get_all(
			step["doctype"], filters={field: doc.name}, pluck="name",
			order_by="creation desc", limit_page_length=1,
		)
	except frappe.PermissionError:
		return None
	return found[0] if found else None


def mapped_values(step, doc):
	"""What carries across from the source record to the new one.

	Only fields the target actually has, and only values that are set - so a blank on the
	lead stays blank on the consumer rather than writing an empty string over a default.
	"""
	meta = frappe.get_meta(step["doctype"])
	out = {}
	for target_field, source in (step.get("map") or {}).items():
		if not meta.get_field(target_field) and target_field != "name":
			continue
		sources = source if isinstance(source, tuple) else (source,)
		for source_field in sources:
			value = doc.name if source_field == "name" else doc.get(source_field)
			if value not in (None, "", 0):
				out[target_field] = value
				break
	for target_field, value in (step.get("defaults") or {}).items():
		if meta.get_field(target_field) and not out.get(target_field):
			out[target_field] = value
	return out


def _card(step, target_name):
	"""The card shown in place of the button once the step is done."""
	doctype = step["doctype"]
	fields = [f for f in (step.get("card_title"), step.get("card_subtitle")) if f and f != "name"]
	values = {}
	if fields:
		values = frappe.db.get_value(doctype, target_name, fields, as_dict=True) or {}

	def pick(key):
		field = step.get(key)
		if not field:
			return ""
		return target_name if field == "name" else (values.get(field) or "")

	return {
		"name": target_name,
		# The card names the kind of document as well as the document, so a person
		# scanning a record's next steps can tell a quotation from a sales order without
		# recognising the numbering series.
		"doctype_label": _(doctype),
		"title": pick("card_title") or target_name,
		"subtitle": pick("card_subtitle"),
		"subtitle_label": step.get("card_subtitle_label", ""),
		"route": "/a3solaportal/{0}/{1}".format(step["slug"], frappe.utils.quote(target_name)),
	}


def steps_for(doc):
	"""Every step from this record, each either an offer to create or the card it became.

	`done` steps show the record they produced. A step whose prerequisite is unmet is
	offered but disabled, so a person can see what comes next before it is reachable.
	"""
	out = []
	done_keys = set()
	for step in steps_of(doc.doctype):
		if not frappe.db.exists("DocType", step["doctype"]):
			continue
		target = find_target(step, doc)
		if target:
			done_keys.add(step["key"])

		blocked_by = step.get("requires")
		blocked = bool(blocked_by) and blocked_by not in done_keys
		note = step.get("requires_note", "") if blocked else ""
		# A mapper reads a submitted document. Offering the step on a draft would only
		# produce an error on the other side, so it is shown disabled with the reason.
		if step.get("needs_submit") and frappe.utils.cint(doc.get("docstatus")) != 1:
			blocked = True
			note = step.get("needs_submit_note", "")

		out.append({
			"key": step["key"],
			"slug": step["slug"],
			"label": step["label"],
			"icon": step["icon"],
			"doctype": step["doctype"],
			"doctype_label": _(step["doctype"]),
			"done": bool(target),
			"card": _card(step, target) if target else None,
			"blocked": blocked and not target,
			"note": note if blocked and not target else "",
			"can_create": frappe.has_permission(step["doctype"], "create"),
			# A mapped step is a write, so it is posted rather than followed as a link.
			"posts": bool(step.get("via")),
			"create_route": "/a3solaportal/{0}/new?source_dt={1}&source={2}".format(
				step["slug"], frappe.utils.quote(doc.doctype), frappe.utils.quote(doc.name)
			),
		})
	return out


def link_back(step, source_doc, target_name):
	"""Record the new document on the source, where the link lives on that side.

	`db_set` rather than `save`, because this is a pointer being recorded and not an edit
	the person made - it must not re-run the source's validation or bump its modified
	timestamp under them. The caller has already checked write permission.
	"""
	link_field = step.get("link_field")
	if not link_field or not source_doc.meta.get_field(link_field):
		return
	if source_doc.get(link_field):
		frappe.throw(
			_("{0} already has a {1}.").format(source_doc.name, step["doctype"]),
			frappe.ValidationError,
		)
	source_doc.db_set(link_field, target_name, update_modified=False)
