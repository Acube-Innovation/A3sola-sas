# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Portal endpoints and field configuration for the Lead doctype.

The list page reads leads server-side in its own `get_context`. This module holds the
two write paths - create and update - because a write needs one guarded place that
validates before it touches the database, and the field configuration the detail and
edit pages share, so what the portal shows and what it lets a person change are decided
once. Nothing here is `allow_guest`: a signed-in user with permission on Lead and a valid
CSRF token are both required before any endpoint is reached.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, fmt_money, format_date, format_datetime, quote, today

from a3_sola.api.portal_fields import INPUT_TYPES, NUMERIC_TYPES, TRUE, detail_row, edit_spec

# The Lead workflow states, mirrored from the doctype. Kept here so the endpoints can
# reject anything off-list rather than trusting whatever the form posted.
LEAD_STATUSES = {
	"Lead", "Open", "Replied", "Opportunity", "Quotation",
	"Lost Quotation", "Interested", "Converted", "Do Not Contact",
}

# The fields the portal shows for one lead, grouped the way a person reads them. Labels
# and types are not repeated here: both come from the doctype meta at render time, so a
# relabelled or missing custom field shows correctly without a change to the portal.
LEAD_SECTIONS = [
	{
		"key": "contact",
		"label": "Contact",
		"fields": ["lead_name", "company_name", "email_id", "mobile_no", "phone", "whatsapp_no", "website", "job_title"],
	},
	{
		"key": "lead",
		"label": "Lead",
		"fields": ["status", "source", "type", "request_type", "qualification_status", "lead_owner", "territory", "industry", "market_segment", "campaign_name"],
	},
	{
		"key": "address",
		"label": "Location",
		"fields": ["city", "state", "country"],
	},
	{
		"key": "solar",
		"label": "Solar details",
		"fields": [
			"subsidy_scheme", "discom", "discom_section", "consumer_number", "consumer_category",
			"connection_type", "roof_type", "approx_consumption_units", "avg_monthly_bill",
			"approx_capacity_kw", "solar_consumer", "solar_proposal",
		],
	},
	{
		"key": "outreach",
		"label": "Outreach",
		"fields": [
			"call_status", "outreach_stage", "solar_lead_status", "last_message_date",
			"next_followup_date", "followup_status", "consecutive_non_connects", "outreach_notes",
		],
	},
]

# Fields the doctype marks read-only that the portal still edits. On the desk the full
# name is composed from first, middle and last name; the portal captures it as one field
# on create and keeps doing so on edit (see `_set_full_name`).
EDITABLE_READ_ONLY = {"lead_name"}

# ------------------------------------------------------------------- routes and loading
def lead_route(name):
	"""The portal detail page for one lead."""
	return "/a3solaportal/leads/{0}".format(quote(name))


def desk_route(name):
	"""The ERPNext desk form, offered as a secondary link for system users."""
	return "/app/lead/{0}".format(quote(name))


def display_name(doc):
	return doc.get("lead_name") or doc.get("company_name") or doc.name


def load_lead(name, permtype="read"):
	"""Load one lead and check the caller may `permtype` it.

	Raises `DoesNotExistError` for an unknown name and `PermissionError` for a lead the
	user may not see, which the website renderer turns into a 404 and a 403 page.
	"""
	name = (name or "").strip()
	if not name or not frappe.db.exists("Lead", name):
		raise frappe.DoesNotExistError(_("That lead does not exist."))
	doc = frappe.get_doc("Lead", name)
	doc.check_permission(permtype)
	return doc


def _visible_fields(meta, section):
	out = []
	for fieldname in section["fields"]:
		df = meta.get_field(fieldname)
		if df and not df.hidden:
			out.append(df)
	return out


# ------------------------------------------------------------------------ detail page
def detail_sections(doc):
	"""The detail page's sections: label plus display-ready rows, in reading order."""
	meta = doc.meta
	sections = []
	for section in LEAD_SECTIONS:
		rows = [detail_row(df, doc.get(df.fieldname)) for df in _visible_fields(meta, section)]
		if rows:
			sections.append({"key": section["key"], "label": section["label"], "rows": rows})
	return sections


# ---------------------------------------------------------------- snapshot and glance
# The at-a-glance rows, in the order a manager reads them. On the edit page a `field`
# row mirrors its form control live; a `static` row is a computed value no form changes.
GLANCE = [
	{"label": "Status", "field": "status", "kind": "badge"},
	{"label": "Lead status", "field": "solar_lead_status"},
	{"label": "Outreach stage", "field": "outreach_stage"},
	{"label": "Call status", "field": "call_status"},
	{"label": "Next follow-up", "field": "next_followup_date", "kind": "date"},
	{"label": "Follow-up", "static": "followup_status", "kind": "followup"},
	{"label": "System size", "field": "approx_capacity_kw", "kind": "number", "suffix": " kW"},
	{"label": "Avg monthly bill", "field": "avg_monthly_bill", "kind": "money"},
	{"label": "Consumer category", "field": "consumer_category"},
]


def currency_of(doc):
	"""(symbol, code) for the lead's company, falling back to the site default."""
	currency = None
	if doc.get("company"):
		currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	currency = currency or frappe.db.get_default("currency") or "INR"
	return frappe.db.get_value("Currency", currency, "symbol") or currency, currency


def glance_rows(doc, only_fields=None):
	"""The at-a-glance rows with display text. `only_fields` limits the mirrored rows to
	fields a form actually renders, so the edit page never shows a pill it cannot update."""
	_symbol, currency = currency_of(doc)
	rows = []
	for spec in GLANCE:
		fieldname = spec.get("field") or spec.get("static")
		df = doc.meta.get_field(fieldname)
		if not df:
			continue
		if spec.get("field") and only_fields is not None and fieldname not in only_fields:
			continue
		value = doc.get(fieldname)
		kind = spec.get("kind", "text")
		if kind == "date":
			text = format_date(value, "medium") if value else ""
		elif kind == "money":
			text = fmt_money(value, currency=currency) if flt(value) else ""
		elif kind == "number":
			text = ("{0:g}".format(flt(value)) + spec.get("suffix", "")) if flt(value) else ""
		else:
			text = value or ""
		rows.append({
			"label": spec["label"],
			"field": spec.get("field"),
			"kind": kind,
			"suffix": spec.get("suffix", ""),
			"text": text,
			"raw": value or "",
		})
	return rows


def lead_snapshot(doc):
	"""Counts and dates for the snapshot card."""
	notes = [n for n in (doc.get("notes") or []) if (n.note or "").strip()]
	return {
		"touches": len(doc.get("outreach_log") or []),
		"notes": len(notes),
		"days_open": max(cint(date_diff(today(), doc.creation)), 0),
		"non_connects": cint(doc.get("consecutive_non_connects")),
		"followup_status": doc.get("followup_status") or "",
		"about": (
			"{0} at {1}.".format(doc.lead_name, doc.company_name)
			if doc.lead_name and doc.company_name and doc.company_name != doc.lead_name
			else "{0}.".format(display_name(doc))
		),
		"created": format_date(doc.creation, "medium"),
		"modified": format_datetime(doc.modified, "medium"),
	}


# -------------------------------------------------------------------------- edit page
def edit_fields(doc):
	"""The fields the edit form renders, with their current values.

	Reused verbatim by `update_lead` as its allow-list, so the two never drift: a field
	the form does not render is a field the endpoint refuses to set.
	"""
	meta = doc.meta
	sections = []
	for section in LEAD_SECTIONS:
		specs = []
		for df in _visible_fields(meta, section):
			if df.fieldtype not in INPUT_TYPES:
				continue
			if df.read_only and df.fieldname not in EDITABLE_READ_ONLY:
				continue
			specs.append(edit_spec(df, doc.get(df.fieldname)))
		if specs:
			sections.append({"key": section["key"], "label": section["label"], "fields": specs})
	return sections


def _set_full_name(doc, full_name):
	"""Store the full name the portal captured as one field.

	The Lead controller recomputes `lead_name` from salutation, first, middle and last
	name on every save when `first_name` is set. The portal edits one field, so a changed
	name must clear the parts or the controller would put the old name straight back.
	"""
	if full_name == (doc.lead_name or ""):
		return
	doc.lead_name = full_name or None
	doc.first_name = None
	doc.middle_name = None
	doc.last_name = None


# ---------------------------------------------------------------------------- endpoints
@frappe.whitelist()
def create_lead(
	lead_name=None,
	company_name=None,
	email_id=None,
	mobile_no=None,
	phone=None,
	status=None,
	source=None,
):
	"""Create a Lead from the portal form and return its name and portal route.

	Mirrors the doctype's own rule - a lead needs a person's name or an organisation's
	name - so the caller gets a clear message here instead of a raw controller error.
	Everything else (permission, naming, the rest of validation) is left to `insert`,
	which is the one authority on whether this user may create the record.
	"""
	lead_name = (lead_name or "").strip()
	company_name = (company_name or "").strip()
	if not lead_name and not company_name:
		frappe.throw(_("Enter a lead name or a company name."), frappe.MandatoryError)

	status = (status or "Lead").strip()
	if status not in LEAD_STATUSES:
		status = "Lead"

	doc = frappe.new_doc("Lead")
	doc.lead_name = lead_name or None
	doc.company_name = company_name or None
	doc.email_id = (email_id or "").strip() or None
	doc.mobile_no = (mobile_no or "").strip() or None
	doc.phone = (phone or "").strip() or None
	doc.status = status
	if (source or "").strip():
		doc.source = source.strip()

	# Permission-checked insert: a user without create rights on Lead is refused here,
	# which is why this endpoint does no role-checking of its own.
	doc.insert()

	return {"name": doc.name, "route": "/a3solaportal/leads"}


@frappe.whitelist()
def update_lead(name=None, **values):
	"""Save the portal edit form onto an existing Lead and return its portal route.

	Only the fields the edit form renders may be set - `edit_fields` is the allow-list -
	and only the ones the caller actually posted are touched, so a partial post changes
	nothing it did not name. Permission and validation are left to `save`, the single
	authority on whether this user may change the record.
	"""
	doc = load_lead(name, "write")
	allowed = {spec["fieldname"]: spec for section in edit_fields(doc) for spec in section["fields"]}

	for fieldname, spec in allowed.items():
		if fieldname not in values:
			continue
		raw = values.get(fieldname)
		if spec["type"] == "Check":
			doc.set(fieldname, 1 if str(raw).lower() in TRUE else 0)
			continue

		text = ("" if raw is None else str(raw)).strip()
		if fieldname == "status":
			if text not in LEAD_STATUSES:
				frappe.throw(_("Choose a valid status."), frappe.ValidationError)
			doc.status = text
		elif fieldname == "lead_name":
			_set_full_name(doc, text)
		elif spec["type"] in NUMERIC_TYPES:
			if not text:
				doc.set(fieldname, None)
			else:
				doc.set(fieldname, cint(text) if spec["type"] == "Int" else flt(text))
		else:
			doc.set(fieldname, text or None)

	if not (doc.lead_name or doc.company_name):
		frappe.throw(_("Enter a lead name or a company name."), frappe.MandatoryError)

	doc.save()

	return {"name": doc.name, "route": lead_route(doc.name)}
