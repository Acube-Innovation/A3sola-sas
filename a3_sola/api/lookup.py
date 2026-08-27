# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Resolve a master by its document name OR by its human title.

Masters are named by series (SOL-SCHM-00001) because the prompts specify a series a tenant
can rebrand. But every caller, every test and every piece of documentation refers to them
by their title - "PM Surya Ghar: Muft Bijli Yojana", "KSEB". Accepting both means the
series is an implementation detail rather than something every caller has to know.
"""

import frappe

#: doctype -> the field holding its human title
TITLE_FIELDS = {
	"Subsidy Scheme": "scheme_name",
	"Electricity Tariff": "tariff_name",
	"DISCOM": "discom_name",
	"DISCOM Section": "section_name",
	"Statutory Fee Schedule": "schedule_name",
	"Solar Package": "specification_code",
	"Component Make": "make_name",
	"Roof Type": "roof_type",
	"Grid Regulation Rule": "rule_code",
	"Outreach Message Template": "template_name",
}


def resolve(doctype, value, company=None):
	"""Return the document name for `value`, which may be a name or a title.

	Returns None when nothing matches, so callers keep their own error messages.
	"""
	if not value:
		return None
	if frappe.db.exists(doctype, value):
		return value

	title_field = TITLE_FIELDS.get(doctype)
	if not title_field:
		return None

	filters = {title_field: value}
	if not frappe.get_meta(doctype).has_field("company"):
		return frappe.db.get_value(doctype, filters, "name")

	# Titles are unique per company, not globally - two tenants each have their own
	# "KSEB". Resolve against the caller's company, then the session default, and only
	# then fall back to any match.
	for candidate in (company, frappe.defaults.get_user_default("Company")):
		if not candidate:
			continue
		match = frappe.db.get_value(doctype, dict(filters, company=candidate), "name")
		if match:
			return match

	# Last resort: any company. Correct on a single-tenant site and the only sensible
	# answer when the session has no default company.
	return frappe.db.get_value(doctype, filters, "name")
