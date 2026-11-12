# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's proposal: made and saved again from a design estimate's builder, and the
older proposal page (new and edit) laid out as the desk form is.

The Solar Design Proposal page lists the proposals; each is made on its design estimate's
page - the details, then the system and commercials of each option, then the Proposal tab
(`proposal_state`, `save_from_estimate`): the proposal's first page, with the saved options
as its estimates, the recommended one the base. An estimate not yet made into a proposal is
listed beside them (`unproposed_estimates`).

The proposal page proper asks for the lead first; its consumer, latest site survey, customer
and site details and every design estimate it has are filled in from it, by the same helpers
the desk form calls (`proposal_defaults_for`, `lead_estimates`). Design Comparison shows
those estimates compared, from `proposal_comparison`. Saving sends only what a person
chooses - the fields below and the estimates in order - and the proposal's own `validate`
works out the rest: the base estimate, the row totals, the offer and the register.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, format_date, today

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
		{"label": "Solar Design Proposal", "href": "/a3solaportal/" + SLUG},
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


def _quoted_part(est, table):
	"""The panel or inverter the estimate is quoted with - not one of its options - as its make,
	size and count: "Rayzon · 550 Wp × 6", "Solinteg · 3.3 kW"."""
	rows = est.get(table) or []
	row = next((r for r in rows if not r.get("is_option")), rows[0] if rows else None)
	if not row:
		return ""
	if table == "panels":
		make, size, count = row.panel_make, flt(row.panel_capacity_wp), cint(row.panel_count or row.nos)
		size = "{0:g} Wp".format(size) if size else ""
	else:
		make, size, count = row.inverter_make, flt(row.inverter_capacity_kw), cint(row.inverter_count or row.nos)
		size = "{0:g} kW".format(size) if size else ""
	if size and count > 1:
		size += " × {0}".format(count)
	make = (frappe.db.get_value("Component Make", make, "make_name") or make) if make else ""
	# The size and count keep together when the cell wraps; the line breaks after the make.
	return " · ".join(p for p in (make, size.replace(" ", " ")) if p)


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
			"panel": _quoted_part(est, "panels"),
			"inverter": _quoted_part(est, "inverters"),
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
def estimate_boms(estimates=None):
	"""The proposal page's BOM tab: each design estimate's Material BOM, Structure BOM and
	Expenses, in the order given - Option 1 the base - read from the estimates as they are now.
	Nothing of it is saved with the proposal; the rows are changed on the estimate."""
	from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import bom_tables

	names = frappe.parse_json(estimates) if isinstance(estimates, str) else (estimates or [])
	blocks = []
	for number, name in enumerate(dict.fromkeys(n for n in names or [] if n), start=1):
		if not frappe.db.exists("Solar Design Estimate", name) or not frappe.has_permission("Solar Design Estimate", "read", name):
			continue
		est = frappe.get_doc("Solar Design Estimate", name)
		blocks.append({
			"number": number, "name": est.name,
			"package": link_title("Solar Package", est.solar_package) if est.solar_package else "",
			"route": "/a3solaportal/design-estimates/{0}/design".format(frappe.utils.quote(est.name)),
			"boms": bom_tables(est),
		})
	if not blocks:
		return ""
	return frappe.render_template("a3_sola/templates/includes/proposal_estimate_boms.html",
		{"blocks": blocks, "money": lambda v: frappe.utils.fmt_money(flt(v), currency="INR")})


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


# ---------------------------------------------------- made from the design estimate
#: What the proposal's first page asks for on the builder's Proposal tab. Who it is for is
#: the estimate's, shown and not asked.
WHO = ("lead", "solar_consumer", "site_survey")
ASKED = ("proposal_date",) + CUSTOMER + LETTER


def design_route_of(proposal):
	"""Where a proposal is edited: step one (Proposal details) of the estimate it quotes - the
	one its base was saved from - from where its options and then its Proposal tab save it
	again. None when that estimate is gone."""
	from a3_sola.api import portal_estimate

	base = frappe.db.get_value(DOCTYPE, proposal, "solar_design_estimate")
	if not base or not frappe.db.exists("Solar Design Estimate", base):
		return None
	return portal_estimate.details_route(portal_estimate.root_of(frappe.get_doc("Solar Design Estimate", base)).name)


def _estimates_of(root):
	"""A root estimate and the estimates its options were saved as."""
	return [root.name] + [r.design_estimate for r in root.get("sizing_options") or [] if r.design_estimate and r.design_estimate != root.name]


def proposal_of(root):
	"""The proposal a root estimate's options are in - the one that quotes any of them, else the
	lead's one proposal - or None while there is none."""
	names = _estimates_of(root)
	found = frappe.db.get_value("Solar Proposal Estimate", {"solar_design_estimate": ["in", names], "parenttype": DOCTYPE,
		"docstatus": ["<", 2]}, "parent")
	if not found:
		found = frappe.db.get_value(DOCTYPE, {"solar_design_estimate": ["in", names], "docstatus": ["<", 2]}, "name")
	if not found and root.lead:
		found = frappe.db.get_value(DOCTYPE, {"lead": root.lead, "docstatus": ["<", 2]}, "name")
	return found


def option_estimates(root):
	"""The options of a root estimate as the proposal's estimates: the recommended first (the
	base), then the rest in tab order, each with the estimate it is saved as - "" while not."""
	from a3_sola.api import portal_estimate

	tabs = portal_estimate.option_tabs(root)
	return [{"key": t["key"], "number": t["number"], "recommended": t["recommended"], "estimate": t["estimate"] or "",
		"package": t["package"], "capacity": t["capacity"], "parts": t["parts"],
		"route": "/a3solaportal/design-estimates/{0}/design".format(frappe.utils.quote(t["estimate"])) if t["estimate"] else ""}
		for t in sorted(tabs, key=lambda t: (not t["recommended"], t["number"]))]


def proposal_state(root):
	"""What the builder's Proposal tab paints: the proposal the options are in, if any; the
	fields of its first page, valued from it, else from the estimate's lead and customer; the
	site details; and the options as its estimates, those not saved yet marked."""
	existing = proposal_of(root)
	doc = frappe.get_doc(DOCTYPE, existing) if existing and frappe.has_permission(DOCTYPE, "read", existing) else None
	lead = root.lead or (frappe.db.get_value("Solar Consumer", root.solar_consumer, "lead") if root.solar_consumer else None)
	defaults = proposal_defaults_for(lead, root.solar_consumer) if (lead or root.solar_consumer) else {}
	if doc:
		values = {f: doc.get(f) for f in EDITABLE}
	else:
		values = {f: defaults.get(f) for f in CUSTOMER}
		values.update({"lead": lead, "solar_consumer": root.solar_consumer or defaults.get("solar_consumer"),
			"site_survey": root.site_survey or defaults.get("site_survey"), "remarks": None})
	values["proposal_date"] = str(values.get("proposal_date") or today())
	sections = _sections(values)
	for section in sections:
		for field in section["fields"]:
			if field["fieldname"] in WHO:
				# The estimate's: shown, not asked.
				field["locked"] = True
				field["display"] = link_title(frappe.get_meta(DOCTYPE).get_field(field["fieldname"]).options, field["value"]) if field["value"] else ""
	sections[0]["note"] = _("Who it is for is the design estimate's. The rest is filled from the lead and its customer; change what the proposal should say.")
	options = option_estimates(root)
	current = doc.versions[-1] if doc and doc.versions else None
	return {
		"existing": {"name": doc.name, "route": record_route(SLUG, doc.name), "status": doc.status or "Draft",
			"issued": doc.docstatus == 1, "has_versions": bool(doc.versions), "current_version": current.version_no if current else 0,
			"next_version": (current.version_no if current else 0) + 1} if doc else None,
		"can_write": bool(doc.has_permission("write") and doc.docstatus < 2) if doc else bool(frappe.has_permission(DOCTYPE, "create")),
		"sections": sections,
		"site": _site(doc or defaults),
		"options": options,
		"unsaved": [o["number"] for o in options if not o["estimate"]],
	}


@frappe.whitelist(methods=["POST"])
def save_from_estimate(name, values):
	"""Make the proposal of a design estimate's options from its builder's Proposal tab, or save
	it again: every option, saved as an estimate, is one of its estimates, the recommended one
	the base. An issued proposal takes the change as a new version. Returns the proposal's page."""
	from a3_sola.api import portal_estimate

	root = portal_estimate.root_of(portal_estimate._load(name, "read"))
	options = option_estimates(root)
	unsaved = [str(o["number"]) for o in options if not o["estimate"]]
	if unsaved:
		frappe.throw(_("Save every option first: Option {0} is not saved as an estimate yet.").format(", ".join(unsaved)),
			title=_("Options Not Saved"))
	lead = root.lead or (frappe.db.get_value("Solar Consumer", root.solar_consumer, "lead") if root.solar_consumer else None)
	if not lead:
		frappe.throw(_("The estimate's customer has no lead, and a proposal belongs to a lead."), frappe.MandatoryError)
	posted = frappe.parse_json(values) or {}
	values = {f: posted.get(f) for f in ASKED if f in posted}
	values.update({"lead": lead, "solar_consumer": root.solar_consumer, "site_survey": root.site_survey})
	existing = proposal_of(root)
	estimates = [o["estimate"] for o in options]
	if existing:
		# Estimates the proposal quotes from elsewhere stay, after these.
		estimates += [r.solar_design_estimate for r in frappe.get_doc(DOCTYPE, existing).get("design_estimates") or []
			if r.solar_design_estimate and r.solar_design_estimate not in estimates]
	return save_proposal(values, estimates, existing)


def unproposed_estimates(limit=100):
	"""The design estimates not yet made into a proposal - the roots whose options are in none -
	newest first, for the Solar Design Proposal list: each opens on its builder."""
	from a3_sola.api import portal_estimate

	quoted = set(frappe.get_all("Solar Proposal Estimate", filters={"parenttype": DOCTYPE, "docstatus": ["<", 2]},
		pluck="solar_design_estimate"))
	quoted |= set(frappe.get_all(DOCTYPE, filters={"docstatus": ["<", 2]}, pluck="solar_design_estimate"))
	rows = frappe.get_list("Solar Design Estimate", filters={"docstatus": ["<", 2], "parent_estimate": ["is", "not set"]},
		fields=["name", "lead", "solar_consumer", "solar_package", "final_capacity_kw", "estimate_date", "modified", "docstatus"],
		order_by="modified desc", limit_page_length=max(limit * 2, 200))
	out = []
	for row in rows:
		options = [o for o in frappe.get_all("Design Estimate Sizing Option", filters={"parent": row.name, "parenttype": "Solar Design Estimate"},
			pluck="design_estimate") if o]
		if row.name in quoted or any(o in quoted for o in options):
			continue
		subject = row.solar_consumer or row.lead
		out.append({
			"name": row.name,
			"customer": link_title("Solar Consumer" if row.solar_consumer else "Lead", subject) if subject else row.name,
			"package": link_title("Solar Package", row.solar_package) if row.solar_package else "",
			"capacity": "{0:g} kW".format(flt(row.final_capacity_kw)) if flt(row.final_capacity_kw) else "",
			"date": format_date(row.estimate_date) if row.estimate_date else "",
			"changed": frappe.utils.format_datetime(row.modified, "d MMM, h:mm a") if row.modified else "",
			"options": len(options) or 1,
			"draft": cint(row.docstatus) == 0,
			"route": portal_estimate.design_route(row.name),
		})
		if len(out) >= limit:
			break
	return out


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
