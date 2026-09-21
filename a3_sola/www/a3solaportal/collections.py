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

import re

import frappe
from frappe import _
from frappe.model.base_document import get_controller

from a3_sola.api import assignments, portal_chain
from a3_sola.www.a3solaportal import fill_shell


# slug -> doctype and its labels. `singular` names the create page ("New consumer").
# title/subtitle/icon mirror the sidebar so the page and the menu never disagree.
COLLECTIONS = {
	"consumers": {"doctype": "Solar Consumer", "title": "Solar Consumer", "singular": "consumer", "subtitle": "Homes and businesses", "icon": "user", "list_sub": "consumer_number"},
	"proposals": {"doctype": "Solar Proposal", "title": "Solar Proposal", "singular": "proposal", "subtitle": "Offer document", "icon": "doc"},
	# An ERPNext Quotation. Its list is metadata-driven like the rest; its create and
	# detail pages are the pricing builder (www/a3solaportal/quotations).
	"quotations": {"doctype": "Quotation", "title": "Quotation", "singular": "quotation", "subtitle": "Priced offer", "icon": "calc"},
	# An ERPNext Sales Order. Created from a quotation by ERPNext's own mapping, so the
	# items and taxes arrive intact; the portal only ever reads and edits the draft.
	"sales-orders": {"doctype": "Sales Order", "title": "Sales Order", "singular": "sales order", "subtitle": "Confirmed orders", "icon": "cart"},
	"design-estimates": {"doctype": "Solar Design Estimate", "title": "Solar Design Estimate", "singular": "design estimate", "subtitle": "System sizing", "icon": "pen"},
	"site-surveys": {"doctype": "Site Survey", "title": "Site Survey", "singular": "site survey", "subtitle": "Roof and load", "icon": "pin"},
	# `form_extra` names fields the create form must render beyond the mandatory ones:
	# the manual result and the reason that goes with it are the point of this form,
	# and neither is mandatory, so neither would be picked up on its own.
	"subsidy-eligibility": {"doctype": "Subsidy Eligibility Check", "title": "Subsidy Eligibility Check", "singular": "eligibility check", "subtitle": "PM Surya Ghar", "icon": "check",
	                        "form_extra": ["result_override", "grid_balance_available", "ineligible_reason"]},
	# ---------------------------------------------------- Solar Operations
	"installations": {"doctype": "Solar Installation", "title": "Solar Installation", "singular": "installation", "subtitle": "The job itself", "icon": "wrench"},
	"installation-tasks": {"doctype": "Installation Task", "title": "Installation Task", "singular": "task", "subtitle": "The thirty tasks", "icon": "checklist"},
	"fee-payments": {"doctype": "Statutory Fee Payment", "title": "Statutory Fee Payment", "singular": "fee payment", "subtitle": "Form 1, Form 2, meter", "icon": "cash"},
	"portal-applications": {"doctype": "Portal Application", "title": "Portal Application", "singular": "portal application", "subtitle": "PM Surya Ghar, CEIG", "icon": "globe"},
	"loan-applications": {"doctype": "Loan Application", "title": "Loan Application", "singular": "loan application", "subtitle": "Financed jobs", "icon": "bank"},
	"agreements": {"doctype": "Solar Agreement", "title": "Solar Agreement", "singular": "agreement", "subtitle": "Stamp paper and terms", "icon": "scroll"},
	"work-orders": {"doctype": "Installation Work Order", "title": "Installation Work Order", "singular": "work order", "subtitle": "Structure and install", "icon": "clipboard"},
	"purchase-orders": {"doctype": "Purchase Order", "title": "Purchase Order", "singular": "purchase order", "subtitle": "Material procurement", "icon": "box"},
	"delivery-notes": {"doctype": "Delivery Note", "title": "Delivery Note", "singular": "delivery note", "subtitle": "Material dispatch", "icon": "truck"},
	"dispatch-notices": {"doctype": "Material Dispatch Notice", "title": "Material Dispatch Notice", "singular": "dispatch notice", "subtitle": "Serials to contractor", "icon": "package"},
	"document-packs": {"doctype": "Document Pack", "title": "Document Pack", "singular": "document pack", "subtitle": "Form 2 and 3, handover", "icon": "stack"},
	"commissioning": {"doctype": "Commissioning Report", "title": "Commissioning Report", "singular": "commissioning report", "subtitle": "Handover reports", "icon": "bolt"},
	"installation-snags": {"doctype": "Installation Snag", "title": "Installation Snag", "singular": "snag", "subtitle": "Defects and rectification", "icon": "alert"},
	"customer-reviews": {"doctype": "Customer Review", "title": "Customer Review", "singular": "customer review", "subtitle": "Feedback and Google", "icon": "star"},
	"subsidy-claims": {"doctype": "Subsidy Claim", "title": "Subsidy Claim", "singular": "subsidy claim", "subtitle": "Request to disbursement", "icon": "wallet"},

	# --------------------------------------------- ERPNext stores and accounts
	# Standard ERPNext documents the operations team works in daily. The app puts its
	# own fields on each of these, which is what makes them part of a solar job
	# rather than generic stock movements.
	"material-requests": {"doctype": "Material Request", "title": "Material Request", "singular": "material request", "subtitle": "Procurement raised", "icon": "request"},
	"purchase-receipts": {"doctype": "Purchase Receipt", "title": "Purchase Receipt", "singular": "purchase receipt", "subtitle": "Goods received", "icon": "inbox"},
	"stock-entries": {"doctype": "Stock Entry", "title": "Stock Entry", "singular": "stock entry", "subtitle": "Issued to site", "icon": "transfer"},
	"serial-numbers": {"doctype": "Serial No", "title": "Serial No", "singular": "serial number", "subtitle": "Modules and inverters", "icon": "barcode"},
	"journal-entries": {"doctype": "Journal Entry", "title": "Journal Entry", "singular": "journal entry", "subtitle": "Accounting adjustments", "icon": "ledger"},

	# ----------------------------------------------------- Solar Projects
	"projects": {"doctype": "Project", "title": "Project", "singular": "project", "subtitle": "Delivery and service", "icon": "briefcase"},
	"billing-plans": {"doctype": "Solar Billing Plan", "title": "Solar Billing Plan", "singular": "billing plan", "subtitle": "Milestones to invoice", "icon": "calendar"},
	"sales-invoices": {"doctype": "Sales Invoice", "title": "Sales Invoice", "singular": "sales invoice", "subtitle": "Raised against milestones", "icon": "receipt"},
	"payment-entries": {"doctype": "Payment Entry", "title": "Payment Entry", "singular": "payment entry", "subtitle": "Money received", "icon": "wallet"},
	"om-contracts": {"doctype": "Solar OM Contract", "title": "Solar OM Contract", "singular": "O&M contract", "subtitle": "Service cover", "icon": "scroll"},
	"om-visits": {"doctype": "Solar OM Visit", "title": "Solar OM Visit", "singular": "O&M visit", "subtitle": "Scheduled maintenance", "icon": "pin"},
	"service-tickets": {"doctype": "Service Ticket", "title": "Service Ticket", "singular": "service ticket", "subtitle": "Faults and requests", "icon": "ticket"},
	"warranty-claims": {"doctype": "Solar Warranty Claim", "title": "Solar Warranty Claim", "singular": "warranty claim", "subtitle": "Against the supplier", "icon": "shield"},
	"generation-readings": {"doctype": "Generation Reading", "title": "Generation Reading", "singular": "generation reading", "subtitle": "Output vs guarantee", "icon": "gauge"},
	"fee-recoveries": {"doctype": "Statutory Fee Recovery", "title": "Statutory Fee Recovery", "singular": "fee recovery", "subtitle": "Fees fronted, recovered", "icon": "refund"},
}

# Company is a tenant concern, set from the user's default rather than asked for.
AUTO_FIELDS = {"company"}
# Field types a plain form can capture. Attach, Table and the rest are handled by noting
# them, not by pretending to render them.
INPUT_TYPES = {"Data", "Select", "Link", "Date", "Datetime", "Int", "Float", "Currency", "Percent", "Check", "Small Text", "Text", "Phone", "Attach Image"}
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


def initials(text):
	"""Up to two initials for an avatar, from the first two words of a name.

	A record with no picture still needs something recognisable in the list, and the
	first letters of the name are what a person scans for.
	"""
	words = [w for w in (text or "").replace("-", " ").split() if w[:1].isalnum()]
	return "".join(w[0] for w in words[:2]).upper() or "?"


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
	# A doctype that names an `image_field` gets a picture in its list; one that names a
	# `list_sub` field gets a second line under the record's name. Both are read from
	# metadata and config, so this stays one list page for every collection.
	image_field = meta.get("image_field") or None
	sub_field = cfg.get("list_sub")
	if sub_field and not meta.get_field(sub_field):
		sub_field = None
	fieldnames = ["name"] + ([meta.title_field] if meta.title_field else []) + [c.fieldname for c in columns]
	fieldnames += [f for f in (image_field, sub_field) if f]
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
			"image": (rec.get(image_field) or "") if image_field else "",
			"initials": initials(primary_text),
			"sub": (rec.get(sub_field) or "") if sub_field else "",
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


def show_when(df):
	"""A simple `depends_on` the portal form can act on, or "" when it cannot.

	Frappe's depends_on is arbitrary JavaScript. The portal evaluates only the one shape
	these forms use - `eval:doc.field=="value"` - and shows the field unconditionally for
	anything else, which errs towards a field being visible rather than silently missing.
	"""
	expr = (df.get("depends_on") or "").strip()
	match = re.match(r'^eval:doc\.([a-z0-9_]+)\s*==\s*["\'](.*)["\']$', expr)
	if not match:
		return ""
	return "{0}={1}".format(match.group(1), match.group(2))


def form_fields(meta, prefill=None, extra=()):
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
	wanted = set(extra or ())
	for f in meta.fields:
		if f.fieldname in AUTO_FIELDS or f.hidden or f.read_only:
			continue
		reqd = bool(f.reqd) or f.fieldname in wanted
		if f.fieldtype not in INPUT_TYPES:
			if reqd and f.fieldtype in ("Attach", "Attach Image", "Table", "Table MultiSelect", "Signature", "Geolocation"):
				unrenderable.append(f.label or f.fieldname)
			continue
		if not reqd and f.fieldtype != "Attach Image":
			if not f.in_list_view or optional >= MAX_OPTIONAL_FORM:
				continue
			optional += 1

		# A field named in `form_extra` is rendered but not demanded.
		spec = {
			"fieldname": f.fieldname, "label": f.label, "type": f.fieldtype,
			"reqd": bool(f.reqd), "show_when": show_when(f),
		}
		seed = (prefill or {}).get(f.fieldname)
		spec["value"] = "" if seed is None else seed
		if f.fieldtype == "Attach Image":
			spec["input"] = "image"
		if f.fieldtype == "Select":
			opts = [o for o in (f.options or "").split("\n")]
			spec["options"] = opts
			# A mandatory Select has to start somewhere, so it falls back to the first real
			# option. An optional one must not: its blank means "not answered", and
			# pre-selecting an option answers it on the person's behalf.
			fallback = next((o for o in opts if o), "") if f.reqd else ""
			spec["default"] = seed or f.default or fallback
		elif f.fieldtype == "Link":
			spec["link_doctype"] = f.options
			choices = link_choices(f.options)
			if seed and not any(c["value"] == seed for c in choices):
				choices.insert(0, {"value": seed, "label": link_title(f.options, seed)})
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
	fields, unrenderable = form_fields(meta, prefill, cfg.get("form_extra") or ())
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
# Every collection has a portal detail page: a record you can open from the menu is a
# record you can read, and one you can edit while it is still a draft.
DETAIL_SLUGS = {
	"consumers", "site-surveys", "design-estimates", "subsidy-eligibility",
	"proposals", "quotations", "sales-orders", "installations",
	"installation-tasks", "fee-payments", "portal-applications", "loan-applications",
	"agreements", "work-orders", "purchase-orders", "delivery-notes",
	"dispatch-notices", "document-packs", "commissioning", "customer-reviews",
	"subsidy-claims", "projects", "billing-plans", "sales-invoices",
	"payment-entries", "om-contracts", "om-visits", "service-tickets",
	"warranty-claims", "generation-readings", "fee-recoveries", "installation-snags",
	"material-requests", "purchase-receipts", "stock-entries", "serial-numbers",
	"journal-entries",
}

#: Slugs whose record may be submitted from the portal. Only the sales order: submitting
#: it is the handoff into Operations - it opens the Solar Installation, its document
#: register and its billing plan - and that is the one place the portal needs to trigger.
#: The CRM steps before it are submitted on the desk, as they always have been.
SUBMIT_SLUGS = {"sales-orders"}

#: Slugs whose detail and create pages are bespoke rather than metadata-driven, so the
#: generic `detail_context` is not what renders them. Quotations open in the pricing
#: builder; they still take part in the chain and in `SLUG_OF_DOCTYPE`.
BESPOKE_SLUGS = {"quotations"}

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
	"site-surveys": [
		("Solar Design Estimate", "Design estimates", "pen", "amber"),
	],
	"subsidy-eligibility": [
		("Solar Proposal", "Proposals", "doc", "amber"),
		("Quotation", "Quotations", "calc", "sky"),
	],
	# No tile for the sales order a quotation became: ERPNext records that link on the
	# order's item rows, not on the order, and these tiles count a Link field. The chain's
	# next-step card finds it by the child row instead, and shows it there.
	"sales-orders": [
		("Solar Installation", "Installations", "wrench", "green"),
	],
}

SKIP_TABS = {"connections", "dashboard"}
MAX_GLANCE = 8


def has_detail(slug):
	return slug in DETAIL_SLUGS


def record_route(slug, name):
	return "/a3solaportal/{0}/{1}".format(slug, frappe.utils.quote(name))


def is_editable(doc):
	"""Whether the portal's edit form may be pointed at this record.

	Write permission is not the whole answer for a submittable doctype: a submitted
	Quotation or Sales Order is closed to `save`, so offering an Edit button on one would
	lead to a form that cannot be saved. A doctype that is not submittable sits at
	docstatus 0 for its whole life, so this is simply write permission for those.
	"""
	return bool(doc.has_permission("write")) and frappe.utils.cint(doc.get("docstatus")) == 0


def load_record(slug, name, permtype="read"):
	"""Load one record of the collection and check the caller may `permtype` it.

	Raises `DoesNotExistError` for an unknown name and `PermissionError` for a record the
	user may not see, which the website renderer turns into a 404 and a 403 page. Asking
	to write a submitted record is refused here rather than at `save`, so the person gets
	the reason instead of a validation error at the end of a form.
	"""
	doctype = get_collection(slug)["doctype"]
	name = (name or "").strip()
	if not name or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("That record does not exist."))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission(permtype)
	if permtype == "write" and frappe.utils.cint(doc.get("docstatus")) != 0:
		frappe.throw(
			_("{0} has been submitted and can no longer be edited here.").format(name),
			frappe.PermissionError,
		)
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
	link_choices, link_title,
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
	context.can_write = is_editable(doc)
	context.edit_route = record_route(slug, doc.name) + "/edit"
	context.list_route = f"/a3solaportal/{slug}"
	# The desk is where a submitted document is amended, so the page still offers a way in.
	context.desk_route = desk_route(doc.doctype, doc.name)
	context.submitted = frappe.utils.cint(doc.get("docstatus")) == 1
	context.can_submit = (
		slug in SUBMIT_SLUGS
		and frappe.utils.cint(doc.get("docstatus")) == 0
		and bool(doc.meta.is_submittable)
		and bool(doc.has_permission("submit"))
	)
	context.back_link = {"href": context.list_route, "label": "Back to " + cfg["title"].lower()}
	context.chain_steps = portal_chain.steps_for(doc)
	# A chain step that ERPNext maps for us is posted from this page, so it needs the
	# record's identity and a CSRF token.
	context.record_doctype = doc.doctype
	context.record_name = doc.name
	context.assignees = assignments.assignees(doc.doctype, doc.name)
	context.csrf_token = frappe.sessions.get_csrf_token()
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
				specs.append(edit_spec(df, doc.get(df.fieldname), doc))
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
