# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's proposal page, new and edit, laid out as the desk form is: two tabs.

Proposal Details asks for the lead first; its consumer, latest site survey, customer and
site details and every design estimate it has are filled in from it, by the same helpers
the desk form calls (`proposal_defaults_for`, `lead_estimates`). Design Comparison shows
those estimates compared, from `proposal_comparison`. Saving sends only what a person
chooses - the fields below and the estimates in order - and the proposal's own `validate`
works out the rest: the base estimate, the row totals, the offer and the register.
"""

import frappe
from frappe import _
from frappe.utils import flt, format_date, today

from a3_sola.api.portal_fields import link_choices, link_title
from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import (
	SITE_FIELDS, lead_estimates, proposal_defaults_for,
)
from a3_sola.www.a3solaportal import fill_shell
from a3_sola.www.a3solaportal.collections import load_record, record_route

SLUG = "proposals"
DOCTYPE = "Solar Proposal"

#: The fields a person sets, by section of the desk form's first tab.
PROPOSAL_FOR = ("lead", "solar_consumer", "site_survey", "proposal_date")
CUSTOMER = ("salutation", "customer_name", "mobile_no", "email_id", "location", "district")
LETTER = ("remarks",)
EDITABLE = PROPOSAL_FOR + CUSTOMER + LETTER
#: Site & Connection shows these as the lead gives them; links read by their title.
SITE_LINKS = {"tariff_code": "KSEB Tariff Category", "discom": "DISCOM", "discom_section": "DISCOM Section"}


# ------------------------------------------------------------------ page
def page_context(context, name=None):
	"""Context for proposals/new (no `name`) and proposals/<name>/edit."""
	doc = _load_for_edit(name) if name else None
	if not doc:
		frappe.has_permission(DOCTYPE, "create", throw=True)
	title = doc.name if doc else _("New proposal")
	crumbs = [
		{"label": "Home", "href": "/a3solaportal/dashboard"},
		{"label": "Solar Proposal", "href": "/a3solaportal/" + SLUG},
	]
	if doc:
		crumbs.append({"label": doc.name, "href": record_route(SLUG, doc.name)})
	crumbs.append({"label": "Edit" if doc else "New"})
	fill_shell(context, active_route="/a3solaportal/" + SLUG, page_title=title, crumbs=crumbs)

	source = _source_estimate()
	if doc:
		values = {f: doc.get(f) for f in EDITABLE}
		state = {
			"site": _site(doc),
			"rows": estimate_rows([r.solar_design_estimate for r in doc.design_estimates]),
			"available": estimate_rows(lead_estimates(doc.lead, doc.solar_consumer)),
			"existing": None,
		}
		# Opened from a design estimate of this lead: it is added as the next option.
		if source and not any(r["name"] == source for r in state["rows"]):
			state["rows"] += [r for r in state["available"] if r["name"] == source]
	else:
		lead = _preset_lead()
		# Opened from a design estimate: its consumer, not only the lead's, and that
		# estimate as the base option - the lead's other estimates stay on offer below.
		consumer, survey = frappe.db.get_value("Solar Design Estimate", source, ["solar_consumer", "site_survey"]) if source else (None, None)
		state = lead_details(lead, consumer) if lead else {"values": {}, "site": _site({}), "rows": [], "available": [], "existing": None}
		if source:
			state["rows"] = [r for r in state["rows"] if r["name"] == source] or estimate_rows([source])
			if survey and lead:
				state["values"]["site_survey"] = survey  # the survey the estimate was designed on
		values = dict(state.pop("values", {}) or {}, lead=lead or "")
	values["proposal_date"] = str(values.get("proposal_date") or today())

	context.record_name = doc.name if doc else ""
	context.issued = bool(doc and doc.docstatus == 1)
	context.next_version = ((doc.versions[-1].version_no if doc.versions else 0) + 1) if doc else 0
	context.has_versions = bool(doc and doc.versions)
	context.title = title
	context.view_route = record_route(SLUG, doc.name) if doc else ""
	context.cancel_route = context.view_route or "/a3solaportal/" + SLUG
	context.sections = _sections(values)
	context.state_json = frappe.as_json(state)
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


def _load_for_edit(name):
	"""The proposal to edit: a draft, or one already submitted - a proposal is revised after
	it is issued, as a new version. A cancelled one has been replaced and is not edited."""
	if not name or not frappe.db.exists(DOCTYPE, name):
		raise frappe.DoesNotExistError(_("That record does not exist."))
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if doc.docstatus == 2:
		frappe.throw(_("{0} was cancelled; edit its amendment instead.").format(name), frappe.PermissionError)
	return doc


def _source_estimate():
	"""The design estimate the page was opened from (?source_dt=Solar Design Estimate&source=), if readable."""
	form = frappe.form_dict
	if (form.get("source_dt") or "").strip() != "Solar Design Estimate":
		return None
	name = (form.get("source") or "").strip()
	if not name or not frappe.db.exists("Solar Design Estimate", name) \
			or not frappe.has_permission("Solar Design Estimate", "read", name):
		return None
	return name


def proposal_action(estimate):
	"""The proposal step from a design estimate, as {label, href, hint}, or None.

	One proposal per lead, so: the proposal the estimate is already in; else the lead's
	proposal, opened with this estimate added as an option (a re-quote is a new version of
	it); else a new proposal, filled from the estimate. None when the user may do none of it.
	"""
	est = frappe.db.get_value("Solar Design Estimate", estimate, ["name", "lead", "solar_consumer"], as_dict=True)
	if not est:
		return None
	query = "?" + frappe.utils.urlencode({"source_dt": "Solar Design Estimate", "source": est.name})
	in_proposal = frappe.db.get_value("Solar Proposal Estimate",
		{"solar_design_estimate": est.name, "parenttype": DOCTYPE, "docstatus": ["<", 2]}, "parent")
	if in_proposal:
		if not frappe.has_permission(DOCTYPE, "read", in_proposal):
			return None
		return {"label": _("View proposal"), "href": record_route(SLUG, in_proposal),
			"hint": _("This estimate is an option of proposal {0}.").format(in_proposal)}
	lead = est.lead or (frappe.db.get_value("Solar Consumer", est.solar_consumer, "lead") if est.solar_consumer else None)
	existing = frappe.db.get_value(DOCTYPE, {"lead": lead, "docstatus": ["<", 2]}, "name") if lead else None
	if existing:
		if not frappe.has_permission(DOCTYPE, "write", existing):
			return None
		return {"label": _("Add to proposal"), "href": record_route(SLUG, existing) + "/edit" + query,
			"hint": _("This lead already has proposal {0}; it opens with this estimate added as an option.").format(existing)}
	if not frappe.has_permission(DOCTYPE, "create"):
		return None
	return {"label": _("Create proposal"), "href": "/a3solaportal/" + SLUG + "/new" + query,
		"hint": _("Opens a new proposal filled in from this estimate.")}


def _preset_lead():
	"""The lead the page opens on: ?lead=, or the lead of the record it was opened from."""
	form = frappe.form_dict
	lead = (form.get("lead") or "").strip()
	source_dt, source = (form.get("source_dt") or "").strip(), (form.get("source") or "").strip()
	if not lead and source_dt == "Lead":
		lead = source
	elif not lead and source_dt and source and frappe.db.exists(source_dt, source) \
			and frappe.has_permission(source_dt, "read", source):
		meta = frappe.get_meta(source_dt)
		if meta.has_field("lead"):
			lead = frappe.db.get_value(source_dt, source, "lead") or ""
		if not lead and meta.has_field("solar_consumer"):
			consumer = frappe.db.get_value(source_dt, source, "solar_consumer")
			lead = frappe.db.get_value("Solar Consumer", consumer, "lead") if consumer else ""
	return lead if lead and frappe.db.exists("Lead", lead) and frappe.has_permission("Lead", "read", lead) else ""


def _sections(values):
	"""Proposal For and Customer as field specs, valued from `values`."""
	meta = frappe.get_meta(DOCTYPE)

	def spec(fieldname):
		df = meta.get_field(fieldname)
		value = values.get(fieldname) or ""
		out = {"fieldname": fieldname, "label": _(df.label), "reqd": bool(df.reqd), "value": str(value),
			"input": {"Link": "select", "Date": "date", "Small Text": "textarea"}.get(df.fieldtype, "text"),
			"hint": _(df.description) if df.description else ""}
		if df.fieldname == "email_id":
			out["input"] = "email"
		if df.fieldtype == "Link":
			choices = _choices(df.options)
			if value and not any(c["value"] == value for c in choices):
				choices.insert(0, {"value": value, "label": link_title(df.options, value)})
			out["options"] = [{"value": "", "label": "—"}] + choices
			out["searchable"] = df.options != "Salutation"
		return out

	return [
		{"title": _("Proposal For"), "fields": [spec(f) for f in PROPOSAL_FOR],
		 "note": _("Choose the lead first: its customer, latest site survey and design estimates are filled in from it.")},
		{"title": _("Customer"), "fields": [spec(f) for f in CUSTOMER],
		 "note": _("Filled from the lead, its customer and site survey.")},
		{"title": _("Covering Letter"), "fields": [spec(f) for f in LETTER], "wide": True,
		 "note": _("The letter lists each design estimate as a point. Anything typed here follows them, one point per line.")},
	]


def _choices(doctype):
	"""Link choices, with what lets the page narrow them: a consumer's lead, a survey's consumer."""
	if doctype == "Solar Consumer":
		rows = frappe.get_list("Solar Consumer", fields=["name", "consumer_name", "lead"], order_by="modified desc", limit_page_length=500)
		leads = {r.name: r.lead for r in rows}
		for lead, consumer in frappe.get_all("Lead", fields=["name", "solar_consumer"],
				filters={"solar_consumer": ["in", list(leads) or [""]]}, as_list=True):
			leads[consumer] = leads.get(consumer) or lead
		return [{"value": r.name, "label": r.consumer_name or r.name, "lead": leads.get(r.name) or ""} for r in rows]
	if doctype == "Site Survey":
		rows = frappe.get_list("Site Survey", fields=["name", "customer_name", "solar_consumer"],
			filters={"docstatus": ["<", 2]}, order_by="creation desc", limit_page_length=500)
		return [{"value": r.name, "label": r.customer_name or r.name, "consumer": r.solar_consumer or "",
			"show_id": bool(r.customer_name)} for r in rows]
	return link_choices(doctype)


def _site(source):
	"""Site & Connection as [{fieldname, label, value}] in the desk form's order, links by title."""
	meta = frappe.get_meta(DOCTYPE)
	out = []
	for fieldname in SITE_FIELDS:
		value = (source or {}).get(fieldname)
		if value and fieldname in SITE_LINKS:
			value = link_title(SITE_LINKS[fieldname], value)
		out.append({"fieldname": fieldname, "label": _(meta.get_field(fieldname).label), "value": value or ""})
	return out


def estimate_rows(names):
	"""Each estimate as the Design Estimates table shows it, readable ones only, in order."""
	rows = []
	for name in dict.fromkeys(n for n in names or [] if n):
		if not frappe.db.exists("Solar Design Estimate", name) or not frappe.has_permission("Solar Design Estimate", "read", name):
			continue
		est = frappe.get_doc("Solar Design Estimate", name)
		total = flt(est.commercials()["total"])
		rows.append({
			"name": est.name,
			"date": format_date(est.estimate_date) if est.estimate_date else "",
			"package": link_title("Solar Package", est.solar_package) if est.solar_package else "",
			"capacity_kw": flt(est.final_capacity_kw),
			"total": total,
			"total_label": frappe.utils.fmt_money(total, currency="INR"),
			"route": "/a3solaportal/design-estimates/{0}/design".format(frappe.utils.quote(est.name)),
			"draft": est.docstatus == 0,
		})
	return rows


# ------------------------------------------------------------------ endpoints
@frappe.whitelist()
def lead_details(lead=None, solar_consumer=None, proposal=None):
	"""What choosing a lead (or then a consumer) fills in, the desk form's `proposal_defaults`
	with the estimates as the table shows them and the lead's proposal if it has one."""
	if not lead:
		return {"values": {}, "site": _site({}), "rows": [], "available": [], "existing": None}
	frappe.has_permission("Lead", "read", lead, throw=True)
	values = proposal_defaults_for(lead, solar_consumer)
	rows = estimate_rows(lead_estimates(lead, values.get("solar_consumer")))
	existing = frappe.db.get_value(DOCTYPE, {"lead": lead, "name": ["!=", proposal or ""], "docstatus": ["<", 2]}, "name")
	return {
		"values": {f: values.get(f) or "" for f in EDITABLE if f in values},
		"site": _site(values),
		"rows": rows,
		"available": rows,
		"existing": {"name": existing, "route": record_route(SLUG, existing)} if existing else None,
	}


@frappe.whitelist()
def save_proposal(values, estimates=None, name=None):
	"""Create the proposal, or save its details, and return its page.

	`values` holds only the fields this page asks for; `estimates` the design estimates in
	order, the first being the base. Everything else - the base estimate field, the row
	totals, the site details, the offer - is filled by the proposal's own `validate`.
	"""
	values = frappe.parse_json(values) or {}
	estimates = frappe.parse_json(estimates) if isinstance(estimates, str) else (estimates or [])
	if name:
		doc = _load_for_edit(name)
	else:
		frappe.has_permission(DOCTYPE, "create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		doc.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	if not (values.get("lead") or "").strip():
		frappe.throw(_("Choose the lead this proposal is for."), frappe.MandatoryError)
	issued = doc.docstatus == 1
	for fieldname in EDITABLE:
		# An issued proposal belongs to its lead and consumer; the rest can change.
		if fieldname in values and not (issued and fieldname in ("lead", "solar_consumer")):
			doc.set(fieldname, (values.get(fieldname) or "").strip() or None)
	doc.set("design_estimates", [])
	for estimate in dict.fromkeys(e for e in estimates if e):
		doc.append("design_estimates", {"solar_design_estimate": estimate})
	if doc.design_estimates:
		doc.solar_design_estimate = doc.design_estimates[0].solar_design_estimate
	if issued:
		_revise(doc)
	elif name:
		doc.save()
	else:
		doc.insert()
	return {"name": doc.name, "route": record_route(SLUG, doc.name)}


@frappe.whitelist()
def pdf(name, download=0):
	"""The proposal as its customer receives it - the Solar Proposal Document print - to read
	in the browser, or to save with `download=1`. Read with the caller's own permissions."""
	from frappe.utils.pdf import get_pdf

	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import proposal_print_format

	doc = load_record(SLUG, name, "read")
	html = frappe.get_print(doc.doctype, doc.name, print_format=proposal_print_format(), no_letterhead=0)
	frappe.local.response.filename = "{0}.pdf".format(doc.get("proposal_file_name") or doc.name)
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"


def _revise(doc):
	"""Save an issued proposal's changes as a revision of it.

	A submitted document skips `validate`, so the steps it would run are run here: the
	site details from the lead, the estimates' rows and totals, the offer. Once a version
	has gone out, the change opens the next one (R2, R3 ...), as Revise does on the record
	page; the version that was sent stays as it was.
	"""
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import _open_version, _save_version_change

	doc.fill_from_lead()
	doc.fill_design_estimates()
	doc.pull_from_estimate()
	doc.compose_file_name()
	if doc.versions:
		_open_version(doc, notes=_("Edited on the portal"))
	_save_version_change(doc)
