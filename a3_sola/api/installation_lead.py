# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a Solar Installation knows once its Lead is chosen.

An installation is opened from the lead. By then the lead has a Solar Consumer, and usually
a site survey, an eligibility check, a design estimate and a proposal; the Details tab is
built from those records rather than typed in again. This resolves which ones they are.

The order of preference mirrors the rest of the app: the proposal names the estimate that
was offered, the estimate names the survey it was sized against, and failing those the
latest live record wins - a submitted one ahead of a draft, as `resolve_subject` on the
design estimate does for surveys.
"""

import frappe

from a3_sola.api import stages
from a3_sola.api.portal_fields import link_title

#: Editable installation fields the consumer seeds while they are still blank.
CONSUMER_DEFAULTS = (
	"customer", "discom", "discom_section", "connection_type", "roof_type",
	"installation_address", "latitude", "longitude",
)


@frappe.whitelist()
def get_lead_context(lead):
	"""What the form fills in when a Lead is picked."""
	frappe.get_doc("Lead", lead).check_permission("read")
	return lead_context(lead)


def lead_context(lead, solar_consumer=None):
	"""The records an installation for `lead` is built from, plus defaults for its fields.

	`solar_consumer` is the consumer already on the installation, if any; it is used when
	the lead itself does not name one.
	"""
	values = frappe.db.get_value(
		"Lead", lead, ["solar_consumer", "solar_proposal", "subsidy_scheme"], as_dict=True
	)
	if not values:
		return {}

	consumer = values.solar_consumer or solar_consumer
	proposal = values.solar_proposal or _latest("Solar Proposal", {"lead": lead})
	estimate = (
		frappe.db.get_value("Solar Proposal", proposal, "solar_design_estimate") if proposal else None
	) or _latest("Solar Design Estimate", {"lead": lead}) or (
		_latest("Solar Design Estimate", {"solar_consumer": consumer}) if consumer else None
	)
	estimate_values = (
		frappe.db.get_value(
			"Solar Design Estimate", estimate,
			["site_survey", "final_capacity_kw", "solar_package", "subsidy_scheme"], as_dict=True,
		)
		if estimate else frappe._dict()
	)
	survey = estimate_values.get("site_survey") or (
		_latest("Site Survey", {"solar_consumer": consumer}) if consumer else None
	)
	eligibility = _latest("Subsidy Eligibility Check", {"lead": lead}) or (
		_latest("Subsidy Eligibility Check", {"solar_consumer": consumer}) if consumer else None
	)

	out = {
		"solar_consumer": consumer,
		"solar_proposal": proposal,
		"solar_design_estimate": estimate,
		"site_survey": survey,
		"subsidy_eligibility_check": eligibility,
		"capacity_kw": estimate_values.get("final_capacity_kw"),
		"solar_package": estimate_values.get("solar_package"),
		"subsidy_scheme": estimate_values.get("subsidy_scheme") or values.subsidy_scheme,
	}
	if consumer:
		out.update(frappe.db.get_value("Solar Consumer", consumer, CONSUMER_DEFAULTS, as_dict=True) or {})
	return out


def lead_of(solar_consumer=None, solar_design_estimate=None, solar_proposal=None):
	"""The lead an installation came from, read back from the records it already links."""
	for doctype, name in (
		("Solar Consumer", solar_consumer),
		("Solar Design Estimate", solar_design_estimate),
		("Solar Proposal", solar_proposal),
	):
		lead = frappe.db.get_value(doctype, name, "lead") if name else None
		if lead:
			return lead
	return None


def consumer_contradicts_lead(lead, solar_consumer):
	"""Whether either record names a different partner than the other.

	Only a contradiction counts. A consumer created before leads were linked names no
	lead, and that is not evidence it belongs to another one.
	"""
	leads_consumer = frappe.db.get_value("Lead", lead, "solar_consumer")
	consumers_lead = frappe.db.get_value("Solar Consumer", solar_consumer, "lead")
	return bool(
		(leads_consumer and leads_consumer != solar_consumer)
		or (consumers_lead and consumers_lead != lead)
	)


def _latest(doctype, filters):
	rows = frappe.get_all(
		doctype,
		filters={**filters, "docstatus": ["<", 2]},
		fields=["name"],
		order_by="docstatus desc, creation desc",
		limit=1,
	)
	return rows[0].name if rows else None


@frappe.whitelist()
def get_installation_preview(lead):
	"""Every value a new installation for `lead` would open with, before it is saved.

	The portal's create page shows the whole desk form once a lead is picked. Rather than
	repeat the desk's fill rules in the browser, this builds the installation in memory
	and runs the same steps its `validate` runs - the lead's records, their fetched
	values, the estimate's design, the package and the statutory fees - then returns the
	result without saving it. What the page shows is therefore what the save will keep.
	"""
	frappe.get_doc("Lead", lead).check_permission("read")
	frappe.has_permission("Solar Installation", "create", throw=True)

	doc = frappe.new_doc("Solar Installation")
	doc.lead = lead
	doc.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")

	warning = None
	try:
		doc.pull_lead_context()
	except frappe.ValidationError as e:
		frappe.clear_messages()
		warning = str(e)
	if not warning:
		doc.copy_estimate_design()
		doc.pull_consumer_defaults()
		doc.apply_package_defaults()
		doc.resolve_template()
		doc.resolve_statutory()
	doc.execution_start_date = doc.execution_start_date or doc.order_date
	# The package and size the Details tab shows for the proposal are the job's own to start with.
	doc.solar_package = doc.solar_package or doc.estimate_package
	doc.capacity_kw = doc.capacity_kw or doc.estimate_capacity_kw
	if doc.stage_template:
		stages.build_stages(doc)

	values, tables, titles = {}, {}, {}
	for df in doc.meta.fields:
		value = doc.get(df.fieldname)
		if df.fieldtype in ("Table", "Table MultiSelect"):
			tables[df.fieldname] = [row.as_dict(convert_dates_to_str=True) for row in (value or [])]
			if df.fieldname == "stages":
				for row in tables["stages"]:
					row["__template"] = 1
		elif df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML"):
			values[df.fieldname] = "" if value is None else str(value) if df.fieldtype in ("Date", "Datetime") else value
			if df.fieldtype == "Link" and value:
				titles[df.fieldname] = link_title(df.options, value)
	return {"values": values, "tables": tables, "titles": titles, "warning": warning}


@frappe.whitelist()
def get_template_tasks(stage_template, execution_start_date=None, order_date=None, is_financed=None,
		subsidy_scheme=None, capacity_kw=None, net_meter_mode=None):
	"""The task rows a stage template gives a job like this one, planned from its start date.

	Called by the create page when the template - or anything that decides which of its
	tasks apply - changes. Built by `stages.build_stages`, the same code the save runs.
	"""
	frappe.has_permission("Solar Installation", "create", throw=True)
	frappe.get_doc("Installation Stage Template", stage_template).check_permission("read")
	doc = frappe.new_doc("Solar Installation")
	doc.update({
		"stage_template": stage_template, "execution_start_date": execution_start_date or None,
		"order_date": order_date or None, "is_financed": frappe.utils.cint(is_financed),
		"subsidy_scheme": subsidy_scheme or None, "capacity_kw": frappe.utils.flt(capacity_kw),
		"net_meter_mode": net_meter_mode or None,
		"company": frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company"),
	})
	stages.build_stages(doc)
	return [{**row.as_dict(convert_dates_to_str=True), "__template": 1} for row in doc.stages]
