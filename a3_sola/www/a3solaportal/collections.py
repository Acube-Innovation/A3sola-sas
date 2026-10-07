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

import os
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
	# Priced extras and concessions on a lead or consumer. Each is a header plus a table of
	# rows: `item_table` names the table the portal edits in place, and `row_amount` tells
	# the page how a row's amount is reached, mirroring the controller, so the running total
	# on screen is the one validate() will save.
	"additional-structures": {"doctype": "Additional Structure", "title": "Additional Structure", "singular": "additional structure",
	                          "subtitle": "Extra mounting work", "icon": "box", "item_table": "items", "row_amount": "qty*rate",
	                          "form_extra": ["solar_design_estimate", "remarks"]},
	"additional-cables": {"doctype": "Additional Cable", "title": "Additional Cable", "singular": "additional cable",
	                      "subtitle": "Extra cable runs", "icon": "bolt", "item_table": "items", "row_amount": "length*rate",
	                      "form_extra": ["solar_design_estimate", "remarks"]},
	"special-discounts": {"doctype": "Special Discount", "title": "Special Discount", "singular": "special discount",
	                      "subtitle": "Approved concessions", "icon": "refund", "item_table": "items", "row_amount": "discount",
	                      "form_extra": ["solar_design_estimate", "approved_by", "reason"]},
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
	# What the portal calls a project is the Solar Installation - the job, as the desk keeps
	# it. `first_tab_first` puts every field of the desk form's first tab at the head of the
	# create form, so the references and identifiers are captured before anything else.
	"projects": {"doctype": "Solar Installation", "title": "Project", "singular": "project", "subtitle": "Delivery and service", "icon": "briefcase",
	             "first_tab_first": True},
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


def _is_status(df):
	"""A status column - `status`, or one named after it, such as `kyc_status` - which the
	list aligns differently from every other column."""
	return df.fieldname == "status" or df.fieldname.endswith("_status")


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
				"status": _is_status(c),
				"badge": c.fieldtype == "Select" and rec.get(c.fieldname) not in (None, ""),
				"route": None,
			})
		rows.append({"cells": cells})

	# headers, matching the cell order above (primary first, then non-title columns)
	headers = [{"label": _("Record"), "num": False, "status": False}]
	for c in columns:
		if c.fieldname == title_field:
			continue
		headers.append({"label": c.label, "num": c.fieldtype in NUMERIC, "status": _is_status(c)})

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
	# A list runs the full width of the page.
	context.main_wide = True
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


def first_tab_fieldnames(meta):
	"""Every field before the doctype's first Tab Break - the desk form's opening tab."""
	names = []
	for df in meta.fields:
		if df.fieldtype == "Tab Break":
			break
		names.append(df.fieldname)
	return names


def form_extra(cfg, meta):
	"""The fields a collection's create form renders beyond the mandatory ones.

	The first tab's fields lead the doctype's field order, so naming them here is enough to
	render them first. `form_fields` still skips the read-only and hidden ones among them.
	"""
	extra = list(cfg.get("form_extra") or ())
	if cfg.get("first_tab_first"):
		extra += first_tab_fieldnames(meta)
	return extra


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
	fields, unrenderable = form_fields(meta, prefill, form_extra(cfg, meta))
	context.collection = {**cfg, "slug": slug}
	context.fields = fields
	context.item_table = item_table(slug, editable=True)
	context.unrenderable = [
		label for label in unrenderable
		if not context.item_table or label != context.item_table["label"]
	]
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
	"journal-entries", "additional-structures", "additional-cables", "special-discounts",
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

#: doctype -> slug, for the collections that have a portal detail page. Solar Installation
#: is listed twice - as "installations" and as "projects" - and opens as a project.
SLUG_OF_DOCTYPE = {COLLECTIONS[s]["doctype"]: s for s in DETAIL_SLUGS if s != "installations"}

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


def form_groups(meta, first_label=None):
	"""The form's layout as [{key, label, sections: [{label, fields: [df]}]}].

	Fields before the first Tab Break form a group named `first_label`, or after the
	doctype; a Section Break without a label continues the section before it. Only fields a
	person can read are kept - no hidden fields, no child tables, no HTML blocks.
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
		# Opened on the form's first Section Break too, so that section keeps its heading.
		if group is None and df.fieldtype != "Column Break" and not groups:
			group = new_group(first_label or meta.name, "details")
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
	for g in form_groups(doc.meta, cfg["title"]):
		sections = []
		for s in g["sections"]:
			rows =[detail_row(df, doc.get(df.fieldname)) for df in s["fields"]]
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
	# A design estimate is edited in its builder, where the system and the prices live.
	context.edit_route = record_route(slug, doc.name) + ("/design" if slug == "design-estimates" else "/edit")
	if slug == "design-estimates":
		context.pdf_route = "/api/method/a3_sola.api.portal_estimate.download_pdf?name=" + frappe.utils.quote(doc.name)
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
	context.item_table = item_table(slug, doc)
	if context.item_table:
		context.extra_template = "templates/includes/portal_item_table.html"
	return context


def edit_fields_for(doc, first_label=None):
	"""The fields the edit form renders, grouped like the form, with current values.

	Reused verbatim by the update endpoint as its allow-list, so the two never drift: a
	field the form does not render is a field the endpoint refuses to set.
	"""
	groups = []
	for g in form_groups(doc.meta, first_label):
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
	context.groups = edit_fields_for(doc, cfg["title"])
	context.view_route = record_route(slug, doc.name)
	context.back_link = {"href": context.view_route, "label": "Back to " + cfg["singular"]}
	context.endpoint = "a3_sola.api.portal_crud.update_record"
	context.item_table = item_table(slug, doc, editable=True)
	context.update(_record_about(doc))
	# The POST is an unsafe method on an authenticated session, so it needs a CSRF token.
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


# ================================================================ line-item tables
# A collection with `item_table` edits that child table on its own create and edit pages,
# as rows in a grid, and shows it on its detail page. The columns are the child doctype's
# own fields; the read-only ones (the row amount) are worked out, never posted.

#: Child field types the rows grid can take as input.
ITEM_INPUT_TYPES = {"Data", "Select", "Int", "Float", "Currency", "Percent"}
ITEM_NUMERIC = {"Int", "Float", "Currency", "Percent"}


def item_table(slug, doc=None, editable=False):
	"""The rows grid for this collection, with `doc`'s rows when there is one, or None.

	`editable` renders it as inputs inside the page's form; otherwise it is a read-only table.
	"""
	cfg = get_collection(slug)
	fieldname = cfg.get("item_table")
	if not fieldname:
		return None
	parent = frappe.get_meta(cfg["doctype"])
	table_df = parent.get_field(fieldname)
	child = frappe.get_meta(table_df.options)
	columns = []
	for df in child.fields:
		if df.hidden or df.fieldtype not in ITEM_INPUT_TYPES:
			continue
		columns.append({
			"fieldname": df.fieldname, "label": _(df.label), "type": df.fieldtype,
			"reqd": bool(df.reqd), "readonly": bool(df.read_only), "default": df.default or "",
			"options": (df.options or "").split("\n") if df.fieldtype == "Select" else None,
			"numeric": df.fieldtype in ITEM_NUMERIC,
		})
	rows, display = [], []
	for row in (doc.get(fieldname) if doc else None) or []:
		rows.append({c["fieldname"]: row.get(c["fieldname"]) for c in columns})
		display.append([
			frappe.format_value(row.get(c["fieldname"]), child.get_field(c["fieldname"]), row) if c["numeric"]
			else (row.get(c["fieldname"]) or "")
			for c in columns
		])
	total = doc.get("total_amount") if doc else 0
	spec = {
		"fieldname": fieldname, "label": _(table_df.label), "reqd": bool(table_df.reqd), "editable": editable,
		"columns": columns, "rows": rows, "display": display, "rule": cfg.get("row_amount") or "",
		"total_label": _(parent.get_label("total_amount")),
		"total": frappe.format_value(total, parent.get_field("total_amount"), doc) if doc else "",
	}
	# What the grid's script starts from, embedded in a <script> tag: "</" is escaped so a
	# row's text can never close that tag.
	spec["json"] = frappe.as_json({k: spec[k] for k in ("columns", "rows", "rule")}).replace("</", "<\\/")
	return spec


def item_rows(slug, posted):
	"""The posted rows, kept to the grid's editable columns: the browser sets nothing else.

	`posted` is the JSON the grid carries in its hidden `__items` input. Blank rows are
	dropped so an untouched last line does not fail validation.
	"""
	spec = item_table(slug)
	if not spec:
		return None
	editable = [c for c in spec["columns"] if not c["readonly"]]
	rows = frappe.parse_json(posted) if isinstance(posted, str) else posted
	out = []
	for row in rows or []:
		if not isinstance(row, dict):
			continue
		clean = {}
		for c in editable:
			value = row.get(c["fieldname"])
			if c["numeric"]:
				clean[c["fieldname"]] = frappe.utils.flt(value) if value not in (None, "") else None
			else:
				clean[c["fieldname"]] = (str(value).strip() or None) if value is not None else None
		# A field still at its default (a unit of "Nos", a type of "Amount") is not an entry.
		if any(not _at_default(c, v) for c, v in zip(editable, clean.values())):
			out.append(clean)
	return spec["fieldname"], out


def _at_default(column, value):
	if value in (None, ""):
		return True
	if column["numeric"]:
		return frappe.utils.flt(value) == frappe.utils.flt(column["default"])
	return str(value) == column["default"]


# ================================================================ lead-first create form
# The project create page mirrors the desk's Solar Installation form: the Lead is asked for
# first and alone, and once it is chosen every tab of the form appears already filled in
# from the records the lead has built up. Fields the desk fetches or computes are shown
# read-only; tables the desk copies from the estimate are shown as they will be copied.

LEAD_FIRST_FIELD = "lead"
#: Estimate tables the project page lets a person add rows to, in a popup, as the estimate does.
EDITABLE_TABLES = ("panels", "inverters", "kseb_expenses", "mounting_expenses", "installation_expenses")
#: Sections the page narrows: only these fields are asked for, and the section leads its tab
#: as a box of its own. The rest of the section is filled on save from the package, the
#: estimate and the panel rows, so it is not put in front of the person.
NARROWED_SECTIONS = {"System Summary": ("solar_package", "capacity_kw")}
#: Sections left off the create page: all worked out once the job is saved and running.
SKIPPED_SECTIONS = ("Progress",)
#: Tabs whose every section is a box of its own.
SPLIT_TABS = ("details", "system", "execution", "commercials")
#: The job's task table: built from the stage template, and added to in a popup.
TASK_TABLE = "stages"
#: Task columns the table shows. The document a task runs in exists only once the job does.
TASK_COLUMNS = ("stage_code", "stage_name", "activity_scope", "status", "planned_start_date", "planned_date",
	"assigned_to", "due_date")


def _child_columns(child_doctype, every_field=False):
	"""Columns for a child table: its list-view fields (else its first few), or all of them."""
	meta = frappe.get_meta(child_doctype)
	usable = [df for df in meta.fields if not df.hidden and df.fieldtype in DISPLAY_TYPES_ALL]
	listed = usable if every_field else ([df for df in usable if df.in_list_view] or usable[:5])
	return [{"fieldname": df.fieldname, "label": df.label, "type": df.fieldtype} for df in listed]


def lead_first_groups(meta):
	"""Every tab and section of the desk form, as specs the create page can render.

	Editable fields become inputs, read-only ones become read-only inputs that only show
	once they hold a value (as the desk hides an empty read-only field), and read-only
	tables become display tables. The lead field itself is returned separately, carrying
	the fields that share its section (the lead's name and mobile) as `companions`, so they
	sit beside it in the first box.
	"""
	lead_spec, groups, group, section, lead_section = None, [], None, None, None

	def open_group(label, key):
		g = {"key": key, "label": label, "sections": []}
		groups.append(g)
		return g

	def open_section(label):
		s = {"label": label or "", "fields": [], "tables": [], "show_when": ""}
		group["sections"].append(s)
		return s

	for df in meta.fields:
		if df.fieldtype == "Tab Break":
			if (df.label or "").strip().lower() in SKIP_TABS:
				group = section = None
				continue
			group, section = open_group(df.label or "Details", frappe.scrub(df.label or df.fieldname)), None
			continue
		if group is None and not groups:
			group = open_group("Details", "details")
		if group is None:
			continue
		if df.fieldtype == "Section Break":
			if df.label or section is None:
				section = open_section(df.label)
				section["show_when"] = show_when_expr(df)
			continue
		if df.fieldtype == "Column Break" or df.hidden or df.fieldname in AUTO_FIELDS:
			continue
		if df.fieldname == "amended_from":
			continue
		if df.fieldname == LEAD_FIRST_FIELD:
			lead_spec = edit_spec(df, None)
			lead_spec["companions"] = []
			lead_section = section
			continue
		if section is None:
			section = open_section("")

		# Read-only tables are copied from the estimate on save, so they are shown as they
		# will arrive. Tables the job builds for itself (tasks, documents, serials) are not.
		if df.fieldtype in ("Table", "Table MultiSelect"):
			if df.fieldname == TASK_TABLE:
				child = frappe.get_meta(df.options)
				section["tables"].append({
					"fieldname": df.fieldname, "label": df.label, "editable": True,
					"columns": [{"fieldname": f, "label": child.get_field(f).label, "type": child.get_field(f).fieldtype}
						for f in TASK_COLUMNS],
				})
			elif df.read_only:
				editable = df.fieldname in EDITABLE_TABLES
				section["tables"].append({
					"fieldname": df.fieldname, "label": df.label, "editable": editable,
					"columns": _child_columns(df.options, every_field=editable),
				})
			continue
		if df.fieldtype not in INPUT_TYPES_ALL or df.fieldtype == "Attach Image":
			continue
		spec = edit_spec(df, None)
		spec["readonly"] = bool(df.read_only)
		spec["show_when"] = show_when_expr(df)
		if spec["readonly"] and df.fieldtype == "Link":
			spec["choices"], spec["many"] = [], True  # displayed, never chosen
		narrowed = NARROWED_SECTIONS.get(section["label"])
		if narrowed and df.fieldname not in narrowed:
			continue
		if lead_section is not None and section is lead_section:
			lead_spec["companions"].append(spec)
		else:
			section["fields"].append(spec)

	for g in groups:
		g["sections"] = [
			s for s in g["sections"] if (s["fields"] or s["tables"]) and s["label"] not in SKIPPED_SECTIONS
		]
	# A tab with nothing to type (Documents, Warranty & Serials) holds only what the job
	# works out once saved, so a new project has nothing to put there.
	groups = [g for g in groups if any(not f["readonly"] for s in g["sections"] for f in s["fields"])]
	for g in groups:
		g["boxes"] = _boxes(g, every_section=g["key"] in SPLIT_TABS)
	return lead_spec, groups


def _boxes(group, every_section=False):
	"""How a tab's sections are laid out as boxes (cards), each with an optional heading.

	A narrowed section (`NARROWED_SECTIONS`) leads its tab in a box of its own. A tab in
	`SPLIT_TABS` gives every section a box of its own. Elsewhere a table - the panels,
	the inverters, each list of expenses - gets its own box headed by its section, and the
	sections between them share one box. That shared box keeps the tab's name as its
	heading only when nothing on the tab was boxed apart, since the tab bar already says it.
	"""
	boxes, shared = [], None
	leading = [s for s in group["sections"] if s["label"] in NARROWED_SECTIONS]
	for s in leading:
		boxes.append({"title": s["label"], "sections": [s]})
	for s in group["sections"]:
		if s in leading:
			continue
		if every_section or (s["tables"] and not s["fields"]):
			boxes.append({"title": s["label"] or group["label"], "sections": [s]})
			shared = None
		else:
			if shared is None:
				shared = {"title": "", "sections": []}
				boxes.append(shared)
			shared["sections"].append(s)
	if len(boxes) == 1 and not boxes[0]["title"]:
		boxes[0]["title"] = group["label"]
	return boxes


def lead_first_allowlist(meta):
	"""The fields the lead-first create endpoint may set: the editable ones on the page."""
	lead_spec, groups = lead_first_groups(meta)
	allowed = {lead_spec["fieldname"]: lead_spec} if lead_spec else {}
	for spec in (lead_spec or {}).get("companions", []):
		if not spec["readonly"]:
			allowed[spec["fieldname"]] = spec
	for g in groups:
		for s in g["sections"]:
			for spec in s["fields"]:
				if not spec["readonly"]:
					allowed[spec["fieldname"]] = spec
	return allowed


def show_when_expr(df):
	"""`show_when` plus the bare truthy form `eval:doc.field`, which the desk uses for checks."""
	rule = show_when(df)
	if rule:
		return rule
	match = re.match(r"^eval:doc\.([a-z0-9_]+)$", (df.get("depends_on") or "").strip())
	return match.group(1) if match else ""


def lead_first_context(context, slug):
	cfg = get_collection(slug)
	meta = frappe.get_meta(cfg["doctype"])
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
	context.collection = {**cfg, "slug": slug}
	context.lead_field, context.groups = lead_first_groups(meta)
	# Arrived from a lead's page: start with it chosen.
	preset = (frappe.form_dict.get("lead") or "").strip()
	if not preset and frappe.form_dict.get("source_dt") == "Lead":
		preset = (frappe.form_dict.get("source") or "").strip()
	if preset and context.lead_field and frappe.db.exists("Lead", preset):
		context.lead_field = {
			**edit_spec(meta.get_field(LEAD_FIRST_FIELD), preset),
			"companions": context.lead_field["companions"],
		}
	# Versioned by the script's own change time: the site's asset version only moves on a
	# build, so an edited script would otherwise be served from the browser's cache.
	context.script_version = int(os.path.getmtime(frappe.get_app_path("a3_sola", "public", "js", "portal_lead_first_form.js")))
	context.row_editor_json = frappe.as_json(row_editor(meta))
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


def row_editor(meta):
	"""What the add-row popup needs for each editable table, and the dropdowns it offers.

	The fields, their choices and which make list follows which variant are the design
	estimate builder's own (`portal_estimate.SECTIONS`), so a row added on the project is
	asked for exactly as it is on the estimate. `computed` are worked out on save.
	"""
	from a3_sola.api.portal_estimate import INPUT, SECTION_BY_KEY, _choices

	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	tables = {}
	for key in EDITABLE_TABLES:
		spec = SECTION_BY_KEY[key]
		child = frappe.get_meta(meta.get_field(key).options)
		fields = []
		for f in spec["fields"]:
			df = child.get_field(f["fieldname"])
			fields.append({
				"fieldname": df.fieldname, "label": _(df.label), "reqd": bool(df.reqd),
				"input": "select" if f.get("choices") else INPUT.get(df.fieldtype, "text"),
				"choices": f.get("choices"), "filter_by": f.get("filter_by"), "default": df.default or "",
			})
		tables[key] = {"label": _(spec["label"]), "fields": fields}
	choices = _choices(frappe._dict(company=company))
	tables[TASK_TABLE] = _task_editor(meta, choices)
	return {"tables": tables, "choices": choices}


def _task_editor(meta, choices):
	"""The task popup: every field a person sets on a task. On a task the template gave the
	job, the template's own fields are shown locked; a task added by hand sets them all."""
	from a3_sola.api.stages import TASK_JOB_FIELDS, TASK_OWN_FIELDS

	child = frappe.get_meta(meta.get_field(TASK_TABLE).options)
	inputs = {"Date": "date", "Int": "number", "Float": "number", "Currency": "number",
		"Check": "check", "Small Text": "textarea", "Text": "textarea"}
	fields = []
	for fieldname in TASK_OWN_FIELDS + TASK_JOB_FIELDS:
		df = child.get_field(fieldname)
		spec = {
			"fieldname": fieldname, "label": _(df.label), "default": df.default or "",
			"reqd": fieldname in ("stage_code", "stage_name"), "locked_on_template": fieldname in TASK_OWN_FIELDS,
			"input": inputs.get(df.fieldtype, "text"),
		}
		if df.fieldtype in ("Select", "Link"):
			key = "task_" + fieldname
			choices[key] = (
				[{"value": o, "label": o} for o in (df.options or "").split("\n") if o]
				if df.fieldtype == "Select" else link_choices(df.options)
			)
			spec.update({"input": "select", "choices": key})
		fields.append(spec)
	return {"label": _("Task"), "fields": fields}
