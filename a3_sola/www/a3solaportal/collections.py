# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Metadata-driven list and create pages for the portal's CRM/Operations doctypes.

Every menu item beyond Leads shows the same two views - a list and a create form - and
they differ only by which doctype they read. Rather than write forty near-identical
files, this module derives both from the doctype's own metadata: the list columns are
the fields the doctype author chose for its list view, and the form fields are its
mandatory and list-view fields. A slug in `COLLECTIONS` is the only per-doctype config.

The create write path lives in `a3_sola.api.portal_crud`, which reuses `form_fields`
here as its allow-list, so the browser can only ever set fields this module renders.
"""

import frappe
from frappe import _
from frappe.model.base_document import get_controller

from a3_sola.api import portal_chain
from a3_sola.www.a3solaportal import fill_shell


# slug -> doctype and its labels. `singular` names the create page ("New consumer").
# title/subtitle/icon mirror the sidebar so the page and the menu never disagree.
COLLECTIONS = {
	"consumers": {"doctype": "Solar Consumer", "title": "Consumers", "singular": "consumer", "subtitle": "Homes and businesses", "icon": "user"},
	"proposals": {"doctype": "Solar Proposal", "title": "Proposals", "singular": "proposal", "subtitle": "Quotes and estimates", "icon": "doc"},
	# An ERPNext Quotation. Its list is metadata-driven like the rest; its create and
	# detail pages are the cost estimate builder (www/a3solaportal/cost-estimates).
	"cost-estimates": {"doctype": "Quotation", "title": "Cost Estimates", "singular": "cost estimate", "subtitle": "Priced quotations", "icon": "calc"},
	"design-estimates": {"doctype": "Solar Design Estimate", "title": "Design Estimates", "singular": "design estimate", "subtitle": "System sizing", "icon": "pen"},
	"site-surveys": {"doctype": "Site Survey", "title": "Site Surveys", "singular": "site survey", "subtitle": "Roof and load", "icon": "pin"},
	"subsidy-eligibility": {"doctype": "Subsidy Eligibility Check", "title": "Subsidy Eligibility", "singular": "eligibility check", "subtitle": "PM Surya Ghar", "icon": "check"},
	"installations": {"doctype": "Solar Installation", "title": "Installations", "singular": "installation", "subtitle": "On-site delivery", "icon": "wrench"},
	"work-orders": {"doctype": "Installation Work Order", "title": "Work Orders", "singular": "work order", "subtitle": "Crew scheduling", "icon": "clipboard"},
	"commissioning": {"doctype": "Commissioning Report", "title": "Commissioning", "singular": "commissioning report", "subtitle": "Handover reports", "icon": "bolt"},
	"net-metering": {"doctype": "Net Metering Agreement", "title": "Net Metering", "singular": "net metering agreement", "subtitle": "DISCOM agreements", "icon": "power"},
	"subsidy-claims": {"doctype": "Subsidy Claim", "title": "Subsidy Claims", "singular": "subsidy claim", "subtitle": "Disbursement tracking", "icon": "wallet"},
}

# Company is a tenant concern, set from the user's default rather than asked for.
AUTO_FIELDS = {"company"}
# Field types a plain form can capture. Attach, Table and the rest are handled by noting
# them, not by pretending to render them.
INPUT_TYPES = {"Data", "Select", "Link", "Date", "Datetime", "Int", "Float", "Currency", "Percent", "Check", "Small Text", "Text", "Phone"}
DISPLAY_TYPES = {"Data", "Select", "Link", "Date", "Datetime", "Int", "Float", "Currency", "Percent", "Check", "Small Text", "Phone"}
TEXTUAL = {"Data", "Select", "Link", "Small Text", "Phone"}
NUMERIC = {"Int", "Float", "Currency", "Percent", "Date", "Datetime"}

MAX_OPTIONAL_FORM = 6
MAX_LIST_COLUMNS = 6
LINK_CHOICE_LIMIT = 50


def get_collection(slug):
	cfg = COLLECTIONS.get(slug)
	if not cfg:
		frappe.throw(_("Unknown collection: {0}").format(slug), frappe.DoesNotExistError)
	return cfg


def desk_route(doctype, name):
	"""The ERPNext desk URL for one record, for collections without a portal detail page."""
	return "/app/{0}/{1}".format(doctype.lower().replace(" ", "-"), frappe.utils.quote(name))


# ---------------------------------------------------------------- list rendering
def _list_columns(meta):
	cols = []
	for f in meta.fields:
		if len(cols) >= MAX_LIST_COLUMNS:
			break
		if f.in_list_view and f.fieldtype in DISPLAY_TYPES and not f.hidden:
			cols.append(f)
	return cols


def _format(value, fieldtype):
	if value in (None, ""):
		return "—"
	if fieldtype == "Check":
		return "Yes" if int(value or 0) else "No"
	if fieldtype == "Date":
		return frappe.utils.format_date(value, "medium")
	if fieldtype == "Datetime":
		return frappe.utils.format_datetime(value, "medium")
	if fieldtype == "Currency":
		return frappe.utils.fmt_money(value)
	if fieldtype == "Percent":
		return "{0}%".format(frappe.utils.flt(value, 1))
	if fieldtype == "Float":
		return frappe.utils.flt(value, 2)
	return value


def list_context(context, slug):
	cfg = get_collection(slug)
	doctype = cfg["doctype"]
	meta = frappe.get_meta(doctype)
	columns = _list_columns(meta)

	q = (frappe.form_dict.get("q") or "").strip()
	fieldnames = ["name"] + ([meta.title_field] if meta.title_field else []) + [c.fieldname for c in columns]
	# de-duplicate while preserving order
	seen, fields = set(), []
	for fn in fieldnames:
		if fn not in seen:
			seen.add(fn)
			fields.append(fn)

	or_filters = None
	if q:
		like = f"%{q}%"
		searchable = ["name"] + [c.fieldname for c in columns if c.fieldtype in TEXTUAL]
		or_filters = [[fn, "like", like] for fn in dict.fromkeys(searchable)]

	records = frappe.get_list(
		doctype, fields=fields, or_filters=or_filters,
		order_by="modified desc", limit_page_length=100,
	)

	title_field = meta.title_field
	rows = []
	for rec in records:
		cells = []
		# primary cell: the doctype's title, or its name, linked to the record
		primary_text = (rec.get(title_field) if title_field else None) or rec.get("name")
		cells.append({
			"text": primary_text, "primary": True, "num": False, "badge": False,
			"route": record_route(slug, rec.get("name")) if has_detail(slug) else desk_route(doctype, rec.get("name")),
		})
		for c in columns:
			if c.fieldname == title_field:
				continue
			cells.append({
				"text": _format(rec.get(c.fieldname), c.fieldtype),
				"primary": False,
				"num": c.fieldtype in NUMERIC,
				"badge": c.fieldtype == "Select" and rec.get(c.fieldname) not in (None, ""),
				"route": None,
			})
		rows.append({"cells": cells})

	# headers, matching the cell order above (primary first, then non-title columns)
	headers = [{"label": _("Record"), "num": False}]
	for c in columns:
		if c.fieldname == title_field:
			continue
		headers.append({"label": c.label, "num": c.fieldtype in NUMERIC})

	fill_shell(
		context,
		active_route=f"/a3solaportal/{slug}",
		page_title=cfg["title"],
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": cfg["title"]}],
	)
	context.collection = {**cfg, "slug": slug}
	context.headers = headers
	context.rows = rows
	context.total = len(rows)
	context.limit = 100
	context.q = q
	return context


# ---------------------------------------------------------------- form rendering
def needs_prompt_name(meta):
	"""Whether the create form must ask the person for the record's id.

	`autoname: Prompt` in the doctype means Frappe expects a name from the caller - but
	only when nothing else supplies one. These doctypes each allocate their own series in
	their controller (SOL-CON-..., RENC-PROP-...), which Frappe runs precisely when no
	name was given. Asking for an id would therefore override the client's own numbering
	with whatever someone typed, so a controller with an `autoname` method is left to it.
	"""
	if (meta.autoname or "").lower() != "prompt":
		return False
	try:
		return not hasattr(get_controller(meta.name), "autoname")
	except Exception:
		return True


def form_fields(meta, prefill=None):
	"""The fields the create form renders, and the mandatory ones it cannot.

	Reused verbatim by the write endpoint as its allow-list, so the two never drift: a
	field the form does not render is a field the API refuses to set. `prefill` seeds the
	rendered values when the record is being created from another one.
	"""
	specs, unrenderable = [], []

	if needs_prompt_name(meta):
		# Prompt naming means the caller supplies the record's own id.
		specs.append({
			"fieldname": "__name", "label": "Reference ID", "type": "Data",
			"reqd": True, "hint": "A unique identifier for this record.",
			"value": (prefill or {}).get("__name", ""),
		})

	optional = 0
	for f in meta.fields:
		if f.fieldname in AUTO_FIELDS or f.hidden or f.read_only:
			continue
		reqd = bool(f.reqd)
		if f.fieldtype not in INPUT_TYPES:
			if reqd and f.fieldtype in ("Attach", "Attach Image", "Table", "Table MultiSelect", "Signature", "Geolocation"):
				unrenderable.append(f.label or f.fieldname)
			continue
		if not reqd:
			if not f.in_list_view or optional >= MAX_OPTIONAL_FORM:
				continue
			optional += 1

		spec = {"fieldname": f.fieldname, "label": f.label, "type": f.fieldtype, "reqd": reqd}
		seed = (prefill or {}).get(f.fieldname)
		spec["value"] = "" if seed is None else seed
		if f.fieldtype == "Select":
			opts = [o for o in (f.options or "").split("\n")]
			spec["options"] = opts
			spec["default"] = seed or f.default or next((o for o in opts if o), "")
		elif f.fieldtype == "Link":
			spec["link_doctype"] = f.options
			try:
				choices = frappe.get_list(f.options, pluck="name", limit_page_length=LINK_CHOICE_LIMIT)
			except frappe.PermissionError:
				choices = []
			if seed and seed not in choices:
				choices.insert(0, seed)
			spec["choices"] = choices
		specs.append(spec)

	return specs, unrenderable


def source_prefill(slug):
	"""(source doc, step, values) when the create page was reached from another record.

	The pairing must be one the chain declares, and the source is read with the caller's
	own permissions, so this cannot be used to read a record the person may not see.
	"""
	source_dt = (frappe.form_dict.get("source_dt") or "").strip()
	source_name = (frappe.form_dict.get("source") or "").strip()
	if not source_dt or not source_name:
		return None, None, {}

	step = portal_chain.find_step(source_dt, slug)
	if not step:
		return None, None, {}
	if not frappe.db.exists(source_dt, source_name):
		return None, None, {}
	doc = frappe.get_doc(source_dt, source_name)
	doc.check_permission("read")
	return doc, step, portal_chain.mapped_values(step, doc)


def new_context(context, slug):
	cfg = get_collection(slug)
	meta = frappe.get_meta(cfg["doctype"])
	source_doc, step, prefill = source_prefill(slug)
	fill_shell(
		context,
		active_route=f"/a3solaportal/{slug}",
		page_title="New " + cfg["singular"],
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": cfg["title"], "href": f"/a3solaportal/{slug}"},
			{"label": "New"},
		],
	)
	fields, unrenderable = form_fields(meta, prefill)
	context.collection = {**cfg, "slug": slug}
	context.fields = fields
	context.unrenderable = unrenderable
	# Carried on the form so the write endpoint can apply the rest of the mapping and
	# record the new document back on the record it came from.
	context.source_dt = source_doc.doctype if source_doc else ""
	context.source_name = source_doc.name if source_doc else ""
	context.source_title = record_title(source_doc) if source_doc else ""
	context.source_route = (
		record_route(SLUG_OF_DOCTYPE[source_doc.doctype], source_doc.name)
		if source_doc and source_doc.doctype in SLUG_OF_DOCTYPE else ""
	)
	if source_doc and source_doc.doctype == "Lead":
		context.source_route = "/a3solaportal/leads/{0}".format(frappe.utils.quote(source_doc.name))
	# The POST is an unsafe method on an authenticated session, so it needs a CSRF token.
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


# ================================================================ record view and edit
# A collection with a portal detail page opens its rows there instead of the desk. The
# page is built from the doctype's own form: each Tab Break is a card, each Section Break
# inside it a sub-heading, so the portal reads the way the ERPNext form does. The desk's
# automatic "Connections" and "Dashboard" tabs are not fields and never appear.
DETAIL_SLUGS = {"consumers", "proposals", "design-estimates", "cost-estimates"}

#: doctype -> slug, for the collections that have a portal detail page.
SLUG_OF_DOCTYPE = {COLLECTIONS[s]["doctype"]: s for s in DETAIL_SLUGS}

# Snapshot tiles: records that link back to this one. (doctype, label, icon, tone).
RECORD_LINKS = {
	"consumers": [
		("Solar Proposal", "Proposals", "doc", "amber"),
		("Site Survey", "Site surveys", "pin", "sky"),
		("Solar Installation", "Installations", "wrench", "green"),
	],
	"proposals": [
		("Quotation", "Quotations", "doc", "sky"),
		("Solar Installation", "Installations", "wrench", "green"),
	],
	"design-estimates": [
		("Solar Proposal", "Proposals", "doc", "amber"),
		("Quotation", "Quotations", "doc", "sky"),
	],
}

SKIP_TABS = {"connections", "dashboard"}
MAX_GLANCE = 8


def has_detail(slug):
	return slug in DETAIL_SLUGS


def record_route(slug, name):
	return "/a3solaportal/{0}/{1}".format(slug, frappe.utils.quote(name))


def load_record(slug, name, permtype="read"):
	"""Load one record of the collection and check the caller may `permtype` it.

	Raises `DoesNotExistError` for an unknown name and `PermissionError` for a record the
	user may not see, which the website renderer turns into a 404 and a 403 page.
	"""
	doctype = get_collection(slug)["doctype"]
	name = (name or "").strip()
	if not name or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("That record does not exist."))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission(permtype)
	return doc


def record_title(doc):
	title_field = doc.meta.title_field
	return (doc.get(title_field) if title_field else None) or doc.name


def form_groups(meta):
	"""The form's layout as [{key, label, sections: [{label, fields: [df]}]}].

	Fields before the first Tab Break form a group named after the doctype; a Section
	Break without a label continues the section before it. Only fields a person can read
	are kept - no hidden fields, no child tables, no HTML blocks.
	"""
	groups, group, section = [], None, None

	def new_group(label, key):
		g = {"key": key, "label": label, "sections": []}
		groups.append(g)
		return g

	for df in meta.fields:
		if df.fieldtype == "Tab Break":
			if (df.label or "").strip().lower() in SKIP_TABS:
				group, section = None, None
				continue
			group = new_group(df.label or "Details", frappe.scrub(df.label or df.fieldname))
			section = None
			continue
		if group is None and df.fieldtype not in ("Section Break", "Column Break") and not groups:
			group = new_group(meta.name, "details")
		if group is None:
			continue  # inside a skipped tab
		if df.fieldtype == "Section Break":
			if df.label or section is None:
				section = {"label": df.label or "", "fields": []}
				group["sections"].append(section)
			continue
		if df.fieldtype == "Column Break":
			continue
		if df.hidden or df.fieldtype not in DISPLAY_TYPES_ALL:
			continue
		if section is None:
			section = {"label": "", "fields": []}
			group["sections"].append(section)
		section["fields"].append(df)

	for g in groups:
		g["sections"] = [s for s in g["sections"] if s["fields"]]
	return [g for g in groups if g["sections"]]


from a3_sola.api.portal_fields import (  # noqa: E402  - grouped with the code that uses it
	DISPLAY_TYPES as DISPLAY_TYPES_ALL, INPUT_TYPES as INPUT_TYPES_ALL, detail_row, edit_spec,
)


def _backlink_field(doctype, target):
	"""The Link field on `doctype` that points at `target`, or None."""
	for df in frappe.get_meta(doctype).get_link_fields():
		if df.options == target:
			return df.fieldname
	return None


def record_snapshot(slug, doc):
	"""Tiles for the snapshot card: linked records, plus age."""
	tiles = []
	for doctype, label, icon, tone in RECORD_LINKS.get(slug, []):
		if not frappe.db.exists("DocType", doctype):
			continue
		field = _backlink_field(doctype, doc.doctype)
		if not field:
			continue
		try:
			count = frappe.db.count(doctype, {field: doc.name})
		except frappe.PermissionError:
			count = 0
		tiles.append({"value": count, "label": label, "icon": icon, "tone": tone})
	tiles.append({
		"value": max(frappe.utils.cint(frappe.utils.date_diff(frappe.utils.today(), doc.creation)), 0),
		"label": "Days on file", "icon": "clipboard", "tone": "sky",
	})
	return tiles


def record_glance(doc):
	"""At-a-glance rows: the status, then the fields the doctype author put in its list view."""
	meta = doc.meta
	rows = []
	seen = set()
	ordered = [meta.get_field("status")] if meta.get_field("status") else []
	ordered += [f for f in meta.fields if f.in_list_view]
	for df in ordered:
		if not df or df.fieldname in seen or df.fieldname == meta.title_field or df.hidden:
			continue
		if df.fieldtype not in DISPLAY_TYPES_ALL or df.fieldtype in ("Small Text", "Text", "Long Text", "Attach", "Attach Image"):
			continue
		seen.add(df.fieldname)
		row = detail_row(df, doc.get(df.fieldname))
		rows.append({"label": df.label, "kind": row["kind"], "text": row["value"], "slug": row.get("slug", "")})
		if len(rows) >= MAX_GLANCE:
			break
	return rows


def _record_about(doc):
	title = record_title(doc)
	return {
		"about": "{0}.".format(title),
		"created": frappe.utils.format_date(doc.creation, "medium"),
		"modified": frappe.utils.format_datetime(doc.modified, "medium"),
	}


def detail_context(context, slug, name):
	cfg = get_collection(slug)
	doc = load_record(slug, name)
	title = record_title(doc)
	fill_shell(
		context,
		active_route=f"/a3solaportal/{slug}",
		page_title=title,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": cfg["title"], "href": f"/a3solaportal/{slug}"},
			{"label": title},
		],
	)
	groups = []
	for g in form_groups(doc.meta):
		sections = []
		for s in g["sections"]:
			rows = [detail_row(df, doc.get(df.fieldname)) for df in s["fields"]]
			sections.append({"label": s["label"] if s["label"] != g["label"] or len(g["sections"]) > 1 else "", "rows": rows})
		groups.append({"key": g["key"], "label": g["label"], "sections": sections})

	rows = [r for g in groups for s in g["sections"] for r in s["rows"]]
	filled = len([r for r in rows if r["kind"] != "empty"])

	context.collection = {**cfg, "slug": slug}
	context.record = doc
	context.title = title
	context.status = doc.get("status") if doc.meta.get_field("status") else None
	context.status_slug = (context.status or "").lower().replace(" ", "-")
	context.groups = groups
	context.filled, context.total = filled, len(rows)
	context.filled_pct = int(round(filled * 100 / len(rows))) if rows else 0
	context.tiles = record_snapshot(slug, doc)
	context.glance = record_glance(doc)
	context.update(_record_about(doc))
	context.can_write = doc.has_permission("write")
	context.edit_route = record_route(slug, doc.name) + "/edit"
	context.list_route = f"/a3solaportal/{slug}"
	context.back_link = {"href": context.list_route, "label": "Back to " + cfg["title"].lower()}
	context.chain_steps = portal_chain.steps_for(doc)
	return context


def edit_fields_for(doc):
	"""The fields the edit form renders, grouped like the form, with current values.

	Reused verbatim by the update endpoint as its allow-list, so the two never drift: a
	field the form does not render is a field the endpoint refuses to set.
	"""
	groups = []
	for g in form_groups(doc.meta):
		sections = []
		for s in g["sections"]:
			specs = []
			for df in s["fields"]:
				if df.fieldtype not in INPUT_TYPES_ALL or df.read_only or df.fieldname in AUTO_FIELDS:
					continue
				specs.append(edit_spec(df, doc.get(df.fieldname)))
			if specs:
				sections.append({"label": s["label"] if s["label"] != g["label"] or len(g["sections"]) > 1 else "", "fields": specs})
		if sections:
			groups.append({"key": g["key"], "label": g["label"], "sections": sections})
	return groups


def edit_allowlist(doc):
	return {spec["fieldname"]: spec for g in edit_fields_for(doc) for s in g["sections"] for spec in s["fields"]}


def edit_context(context, slug, name):
	cfg = get_collection(slug)
	doc = load_record(slug, name, "write")
	title = record_title(doc)
	fill_shell(
		context,
		active_route=f"/a3solaportal/{slug}",
		page_title="Edit " + title,
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": cfg["title"], "href": f"/a3solaportal/{slug}"},
			{"label": title, "href": record_route(slug, doc.name)},
			{"label": "Edit"},
		],
	)
	context.collection = {**cfg, "slug": slug}
	context.record = doc
	context.title = title
	context.groups = edit_fields_for(doc)
	context.view_route = record_route(slug, doc.name)
	context.back_link = {"href": context.view_route, "label": "Back to " + cfg["singular"]}
	context.endpoint = "a3_sola.api.portal_crud.update_record"
	context.update(_record_about(doc))
	# The POST is an unsafe method on an authenticated session, so it needs a CSRF token.
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
