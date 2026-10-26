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

from a3_sola.api import assignments, installation_lead, portal_chain
from a3_sola.www.a3solaportal import fill_shell


# slug -> doctype and its labels. `singular` names the create page ("New consumer").
# title/subtitle/icon mirror the sidebar so the page and the menu never disagree.
COLLECTIONS = {
	# The installation site and the permanent address - asked for only when it is not the
	# installation site (its show-when rule) - are not mandatory, so would not be picked up
	# on their own.
	"consumers": {"doctype": "Solar Consumer", "title": "Customer", "singular": "customer", "subtitle": "Homes and businesses", "icon": "user", "list_sub": "consumer_number",
	              "form_extra": ["site_address_line1", "site_address_line2", "site_city", "site_state", "site_district",
	                             "site_pincode", "permanent_address_line1", "permanent_address_line2", "permanent_city",
	                             "permanent_state", "permanent_district", "permanent_pincode"]},
	"proposals": {"doctype": "Solar Proposal", "title": "Solar Proposal", "singular": "proposal", "subtitle": "Offer document", "icon": "doc"},
	# An ERPNext Quotation. Its list is metadata-driven like the rest; its create and
	# detail pages are the pricing builder (www/a3solaportal/quotations).
	"quotations": {"doctype": "Quotation", "title": "Quotation", "singular": "quotation", "subtitle": "Priced offer", "icon": "calc"},
	# An ERPNext Sales Order. Created from a quotation by ERPNext's own mapping, so the
	# items and taxes arrive intact; the portal only ever reads and edits the draft.
	# ERPNext refuses an order without a delivery date though its field is not marked so.
	"sales-orders": {"doctype": "Sales Order", "title": "Sales Order", "singular": "sales order", "subtitle": "Confirmed orders", "icon": "cart",
		"required": ("delivery_date",),
		# A week from today, on a working day; the person may change it, but not to a weekend.
		"defaults": {"delivery_date": "a3_sola.overrides.sales_order.default_delivery_date"},
		"no_weekend": ("delivery_date",)},
	"design-estimates": {"doctype": "Solar Design Estimate", "title": "Solar Design Estimate", "singular": "design estimate", "subtitle": "System sizing", "icon": "pen",
	                     "list_filters": ["solar_consumer"], "search_hint": "Search by customer name, estimate, lead or site survey ID",
	                     "list_edit": True},
	# `edit_after_create`: the create form asks only the few fields a record needs to exist,
	# so once it does, the person goes straight on to its full edit form.
	"site-surveys": {"doctype": "Site Survey", "title": "Site Survey", "singular": "site survey", "subtitle": "Roof and load", "icon": "pin",
	                 "edit_after_create": True},
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
	# The procurement tasks' material lists are a rows grid, each on the task that buys it.
	"installation-tasks": {"doctype": "Installation Task", "title": "Installation Task", "singular": "task", "subtitle": "The thirty tasks", "icon": "checklist",
	                       "item_table_by": ("task_code", {"SPROC": "structure_materials", "PROC": "materials"}), "item_total": False},
	"fee-payments": {"doctype": "Statutory Fee Payment", "title": "Statutory Fee Payment", "singular": "fee payment", "subtitle": "Form 1, Form 2, meter", "icon": "cash"},
	"portal-applications": {"doctype": "Portal Application", "title": "Portal Application", "singular": "portal application", "subtitle": "PM Surya Ghar, CEIG", "icon": "globe"},
	"loan-applications": {"doctype": "Loan Application", "title": "Loan Application", "singular": "loan application", "subtitle": "Financed jobs", "icon": "bank"},
	"agreements": {"doctype": "Solar Agreement", "title": "Solar Agreement", "singular": "agreement", "subtitle": "Stamp paper and terms", "icon": "scroll"},
	"work-orders": {"doctype": "Installation Work Order", "title": "Installation Work Order", "singular": "work order", "subtitle": "Structure and install", "icon": "clipboard"},
	"purchase-orders": {"doctype": "Purchase Order", "title": "Purchase Order", "singular": "purchase order", "subtitle": "Material procurement", "icon": "box"},
	"delivery-notes": {"doctype": "Delivery Note", "title": "Delivery Note", "singular": "delivery note", "subtitle": "Material dispatch", "icon": "truck"},
	"dispatch-notices": {"doctype": "Material Dispatch Notice", "title": "Material Dispatch Notice", "singular": "dispatch notice", "subtitle": "Serials to contractor", "icon": "package"},
	"document-packs": {"doctype": "Document Pack", "title": "Document Pack", "singular": "document pack", "subtitle": "Form 2, Form 3, handover", "icon": "stack"},
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
	"reimbursements": {"doctype": "Expense Reimbursement", "title": "Reimbursement", "singular": "reimbursement", "subtitle": "Claims, approval, payment", "icon": "wallet"},
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


def _link_titles(doctype, names):
	"""name -> title for the records of `doctype` a page shows, in one query.

	A doctype with no title field - a survey, say - keeps its ids; they are what it is called.
	"""
	names = {n for n in names if n}
	if not names:
		return {}
	try:
		title_field = frappe.get_meta(doctype).title_field
	except Exception:
		return {}
	if not title_field or title_field == "name":
		return {}
	rows = frappe.get_all(doctype, filters={"name": ("in", list(names))}, fields=["name", title_field], limit_page_length=0)
	return {r["name"]: r.get(title_field) or r["name"] for r in rows}


def _link_images(doctype, names):
	"""name -> picture URL for the records of `doctype` a page shows, in one query.

	Read from the doctype's own `image_field` - a consumer's photograph, a lead's image -
	so a survey or an estimate listed under a person shows the same face their page does.
	"""
	names = {n for n in names if n}
	if not names:
		return {}
	try:
		image_field = frappe.get_meta(doctype).get("image_field")
	except Exception:
		return {}
	if not image_field:
		return {}
	rows = frappe.get_all(doctype, filters={"name": ("in", list(names))}, fields=["name", image_field], limit_page_length=0)
	return {r["name"]: r.get(image_field) or "" for r in rows}


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


def _names_like(doctype, like, limit=200):
	"""The records of `doctype` whose name, title or search fields match, read with the
	caller's own permissions. For a Lead, its person's name and its company's."""
	meta = frappe.get_meta(doctype)
	fields = [meta.title_field] + [f.strip() for f in (meta.search_fields or "").split(",")]
	if doctype == "Lead":
		fields += ["lead_name", "company_name"]
	fields = [f for f in dict.fromkeys(fields) if f and f != "name" and meta.get_field(f)
		and meta.get_field(f).fieldtype in ("Data", "Small Text", "Phone", "Select")]
	if not fields:
		return []
	try:
		return frappe.get_list(doctype, or_filters=[[f, "like", like] for f in fields], pluck="name", limit_page_length=limit)
	except frappe.PermissionError:
		return []


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
	# A doctype with no title of its own is listed under the person it is for, with its
	# id beneath - the way a survey or an estimate is spoken of.
	title_field = meta.title_field if meta.title_field and meta.title_field != "name" else None
	person = person_link(meta) if not title_field else None
	fieldnames = ["name"] + ([title_field] if title_field else []) + [c.fieldname for c in columns]
	fieldnames += [f for f in (image_field, sub_field, person.fieldname if person else None) if f]
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
		# A linked record is searched by its name as well as its id: "Shiju" finds the
		# estimates of the consumer Mr Shiju, not only those whose ids contain it.
		for df in [c for c in columns if c.fieldtype == "Link"] + ([person] if person else []):
			matches = _names_like(df.options, like)
			if matches:
				or_filters.append([df.fieldname, "in", matches])

	# Narrowed to one linked record - the consumer, say - chosen from the list's filter.
	filters, list_filters = {}, []
	for fieldname in cfg.get("list_filters") or []:
		df = meta.get_field(fieldname)
		if not df or df.fieldtype != "Link":
			continue
		chosen = (frappe.form_dict.get(fieldname) or "").strip()
		if chosen:
			filters[fieldname] = chosen
		list_filters.append({"fieldname": fieldname, "label": _(df.label), "value": chosen,
			"choices": link_choices(df.options)})

	# A cancelled document has been withdrawn or replaced by its amendment (the proposal's
	# "-1"), so the list shows what stands; the cancelled one still opens from its link.
	if meta.is_submittable:
		filters["docstatus"] = ["<", 2]
	# `list_edit`: an Edit column, linking each record the person may still change to where
	# it is edited - a draft, for a submittable doctype, as the record's own Edit button.
	list_edit = bool(cfg.get("list_edit")) and frappe.has_permission(doctype, "write")
	if list_edit and meta.is_submittable and "docstatus" not in fields:
		fields.append("docstatus")
	records = frappe.get_list(
		doctype, fields=fields, filters=filters, or_filters=or_filters,
		order_by="modified desc", limit_page_length=100,
	)

	# Every linked record on the page, named: one query per linked doctype, not one per cell.
	link_columns = [c for c in columns if c.fieldtype == "Link"] + ([person] if person else [])
	titles = {}
	for df in link_columns:
		titles.setdefault(df.options, {}).update(
			_link_titles(df.options, {rec.get(df.fieldname) for rec in records})
		)

	# A record named after a person wears that person's picture, as the Consumer list does.
	images = _link_images(person.options, {rec.get(person.fieldname) for rec in records}) if person else {}

	# The person column says what the primary cell already says, so it is not repeated.
	shown = [c for c in columns if c.fieldname != title_field and not (person and c.fieldname == person.fieldname)]

	rows = []
	for rec in records:
		cells = []
		# primary cell: the record's title, else who it is for, else its id - linked to it
		name = rec.get("name")
		primary_text = (rec.get(title_field) if title_field else None) or (
			titles.get(person.options, {}).get(rec.get(person.fieldname)) if person and rec.get(person.fieldname) else None
		) or name
		cells.append({
			"text": primary_text, "primary": True, "num": False, "badge": False,
			"route": record_route(slug, name) if has_detail(slug) else desk_route(doctype, name),
			"image": ((rec.get(image_field) or "") if image_field else "")
				or (images.get(rec.get(person.fieldname)) or "" if person else ""),
			"initials": initials(primary_text),
			"sub": ((rec.get(sub_field) or "") if sub_field else "") or (name if primary_text != name else ""),
		})
		for c in shown:
			value = rec.get(c.fieldname)
			if c.fieldtype == "Link" and value:
				text = titles.get(c.options, {}).get(value) or value
			else:
				text = _format(value, c.fieldtype)
			cells.append({
				"text": text,
				"primary": False,
				"num": c.fieldtype in NUMERIC,
				"status": _is_status(c),
				"badge": c.fieldtype == "Select" and value not in (None, ""),
				"route": None,
			})
		if list_edit:
			editable = not meta.is_submittable or frappe.utils.cint(rec.get("docstatus")) == 0
			cells.append({"text": _("Edit") if editable else "—", "edit": editable, "primary": False, "num": False,
				"status": False, "badge": False, "route": edit_route(slug, name) if editable else None})
		rows.append({"cells": cells})

	# headers, matching the cell order above (primary first, then the columns shown)
	headers = [{"label": _("Name"), "num": False, "status": False}]
	for c in shown:
		headers.append({"label": c.label, "num": c.fieldtype in NUMERIC, "status": _is_status(c)})
	if list_edit:
		headers.append({"label": _("Edit"), "num": False, "status": False})

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
	context.list_filters = list_filters
	context.filtered = bool(filters)
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


#: Fields the portal never shows, by doctype: ERPNext sets them itself (an order's
#: currency and exchange rates come from the company, customer and price list), or they
#: are the office's business, kept in ERPNext (a task's cost).
PORTAL_HIDDEN = {
	"Sales Order": {"currency", "conversion_rate", "plc_conversion_rate"},
	"Installation Task": {"cost", "cost_category", "cost_remarks"},
	"Document Pack": {"task_cost"},
}


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
	hidden = PORTAL_HIDDEN.get(meta.name, set())
	for f in meta.fields:
		if f.fieldname in AUTO_FIELDS or f.hidden or f.read_only or f.fieldname in hidden:
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
			if not seed:
				seed = default_for(f)
				if seed:
					spec["value"] = seed
			rule = DEPENDENT_LINKS.get(f.fieldname)
			spec["depends_field"] = rule[1] if rule else ""
			spec["depends_also"] = ",".join(source for _t, source, _r in DEPENDENT_ALSO.get(f.fieldname, ()))
			choices = link_choices(f.options, filters=link_filters(f, frappe._dict(prefill or {})))
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


def task_source(slug, installation, task_code):
	"""What a task's document starts with when it is created from the project board, or None.

	The values the desk's Task button opens a new document with (`tasks.open_task`): the job,
	its consumer, the task code and the kind of document the task needs. Only for this
	collection's doctype, and only while the task has no document yet; the job is read with
	the caller's own permissions.
	"""
	from a3_sola.api import tasks

	if not (installation and task_code and frappe.db.exists("Solar Installation", installation)):
		return None
	target = tasks.open_task(installation, task_code, create_draft=0)
	if target.get("name") or target.get("doctype") != get_collection(slug)["doctype"]:
		return None
	return {k: v for k, v in (target.get("route_options") or {}).items() if v not in (None, "")}


#: What a task's document is opened with that makes it that task's: the job, the task code
#: and the kind of document the task needs. Fixed on the task's create form - carried, shown
#: as context, never edited - while the rest of its values (a loan's lender) can be changed.
TASK_FIXED = (
	"solar_installation", "solar_consumer", "company", "task_code",
	"fee_type", "pack_type", "application_type", "work_order_kind", "work_order_type",
	# Who it is with is the task's people, set in its Assigned to strip; the document takes
	# the lead of them.
	"assigned_to",
	# A task's document is named for its task.
	"task_name",
)


#: Tasks whose create form asks only for these fields, by task code; the rest of the
#: document is filled in later, on its edit form. Registering on the PM Surya Ghar portal
#: is its number, date and who applied - the approval comes afterwards.
TASK_FORM_FIELDS = {
	"NPA": ("application_number", "application_date", "applied_by"),
	# Buying the stamp paper: bought or not, what it cost, whether it is claimed back - the
	# rest of the agreement comes later.
	"STMP": ("stamp_paper_status", "stamp_paper_value", "claim_reimbursement", "stamp_paper_remarks"),
	# Paying the Form 1 application fee: paid or not, who paid it (TASK_FORM_CHOICES), a
	# remark - the amount is the fee schedule's, and the receipt goes on the task's Documents.
	"F1PAY": ("payment_completed", "paid_by", "remarks"),
}

#: Fields a task's create form asks as one choice that sets several fields, by task code:
#: {code: {field: ((label, {field: value}), ...)}}. A choice that raises a reimbursement
#: (it sets a REIMBURSEMENT_FIELDS field) is offered only where the task allows one.
TASK_FORM_CHOICES = {
	# The company's payment made from someone's own pocket is "I paid", claimed back as the
	# stamp paper is; the customer recovery is the company's either way.
	"F1PAY": {"paid_by": (
		("Company", {"paid_by": "Company on Behalf of Customer", "claim_reimbursement": 0}),
		("Customer", {"paid_by": "Customer Directly", "claim_reimbursement": 0}),
		("I paid - Claim Reimbursement", {"paid_by": "Company on Behalf of Customer", "claim_reimbursement": 1}),
	)},
}

#: Select fields a task's create form asks as a single tick box, by task code:
#: {code: {field: (label, value when ticked, value when not)}}.
TASK_FORM_CHECKS = {
	"STMP": {"stamp_paper_status": ("Stamp paper purchased", "Purchased", "Not Purchased")},
}

#: A task form field shown only where the task allows a reimbursement.
REIMBURSEMENT_FIELDS = {"claim_reimbursement"}

#: Show-when rules on a task's create form, by task code: {code: {field: rule}}.
TASK_FORM_SHOW_WHEN = {
	# Claimed back only once it is bought.
	"STMP": {"claim_reimbursement": "stamp_paper_status"},
	"F1PAY": {"paid_by": "payment_completed"},
}


#: Tasks whose own form asks about a reimbursement (the stamp paper's "I paid" box), so
#: their create form needs no Claim reimbursement button.
CLAIM_IN_FORM = {"STMP", "F1PAY"}


def tasks_code_for(doc):
	from a3_sola.api.tasks import code_for

	return code_for(doc)


def task_claim(installation, task_code):
	"""What a task's reimbursement button needs, or None when there is no task: the claim the
	person has already raised for it (not rejected), to view - and edit while it waits for
	approval, on its page - else what a new claim is raised against."""
	if not (installation and task_code):
		return None
	name = frappe.db.get_value(
		"Installation Stage Log", {"parent": installation, "parenttype": "Solar Installation", "stage_code": task_code},
		"stage_name",
	)
	if not name:
		return None
	existing = frappe.db.get_value(
		"Expense Reimbursement",
		{"solar_installation": installation, "task_code": task_code, "claimant": frappe.session.user,
		 "status": ("!=", "Rejected")},
		["name", "status"], as_dict=True, order_by="creation desc",
	)
	# A claim already raised is always there to view; a new one only where the task allows it.
	if not existing and not reimbursable(installation, task_code):
		return None
	return {
		"installation": installation, "task": task_code, "task_name": name,
		"existing": {**existing, "route": record_route("reimbursements", existing.name)} if existing else None,
	}


def reimbursable(installation, task_code):
	"""Whether the job's task template ticks Allow Reimbursement for this task."""
	template = frappe.db.get_value("Solar Installation", installation, "stage_template")
	if not template:
		return False
	# A plain query: get_all drops some template-row columns from its field list.
	rows = frappe.db.sql(
		"""select allow_reimbursement from `tabInstallation Stage Template Detail`
		where parent = %s and parenttype = 'Installation Stage Template' and stage_code = %s""",
		(template, task_code),
	)
	return bool(rows and rows[0][0])


def task_people(installation, task_code):
	"""Who a task is assigned to - its people on the job, the defaults from its position
	first - for the Assigned to strip on the task's own pages. None when there is no task."""
	if not (installation and task_code):
		return None
	name = frappe.db.get_value(
		"Installation Stage Log", {"parent": installation, "parenttype": "Solar Installation", "stage_code": task_code},
		["stage_name", "default_assignee"], as_dict=True,
	)
	if not name:
		return None
	rows = frappe.get_all(
		"Installation Task Assignee", filters={"parent": installation, "parenttype": "Solar Installation", "stage_code": task_code},
		fields=["user", "full_name"], order_by="idx asc",
	)
	return {
		"installation": installation, "task": task_code, "task_name": name.stage_name,
		"position": name.default_assignee or "",
		"assignees": [{"user": r.user, "name": r.full_name or r.user} for r in rows],
		"can_assign": bool(frappe.has_permission("Solar Installation", "write", installation)),
	}


def task_missing(installation, task_code):
	"""What a task's document is still missing from the job, for its page to say, or None:
	Form 1's (and Forms 2 and 3's - the same) row 1 details the customer's record does not have
	yet (api/form1_print), with a link to fill them in."""
	form = {"FRM1": "Form 1", "FRM2": "Form 2", "KFORMS": "Form 3"}.get(task_code)
	if not form or not installation:
		return None
	from a3_sola.api import form1_print

	items = form1_print.missing(installation)
	if not items:
		return None
	consumer = frappe.db.get_value("Solar Installation", installation, "solar_consumer")
	return {
		"title": "{0} is missing the customer's details in row 1".format(form),
		"note": "Fill them on the customer's page, then view {0} again.".format(form),
		"items": items,
		"href": edit_route("consumers", consumer) if consumer else "",
		"label": "Fill in on the customer's page",
	}


def task_downloads(installation, task_code, document=None):
	"""What a task offers to download before or after its document exists: the stamp paper
	data the vendor writes the paper from (api/stamp_print.py); the structure material
	and material tasks' purchase lists, once the task is saved (api/purchase_list.py); KSEBL
	Forms 1, 2 and 3 with the customer's details, to view or download (api/form1_print.py,
	api/form2_print.py, api/form3_print.py)."""
	if task_code == "FRM1":
		from a3_sola.api import form1_print

		return [{"label": "View Form 1", "url": form1_print.url(installation), "icon": "eye"},
			{"label": "Download Form 1", "url": form1_print.url(installation, download=True)}]
	if task_code == "FRM2":
		from a3_sola.api import form2_print

		return [{"label": "View Form 2", "url": form2_print.url(installation), "icon": "eye"},
			{"label": "Download Form 2", "url": form2_print.url(installation, download=True)}]
	if task_code == "KFORMS":
		# Each of the Form 3 papers the job prints, as its task row offers it: view, download.
		from a3_sola.api import portal_tasks

		prints = portal_tasks._prints(frappe._dict(stage_code="KFORMS"), installation)
		return [{"label": p["label"], "url": p["url"], **({"icon": "eye"} if i == 0 else {})}
			for links in prints.values() for i, p in enumerate(links)]
	if task_code == "STMP":
		from a3_sola.api import stamp_print

		return [{"label": "Download stamp paper data", "url": stamp_print.url(installation, document)}]
	if task_code in ("SPROC", "PROC") and document:
		from a3_sola.api import purchase_list

		return [{"label": "Download purchase list", "url": purchase_list.url(document, download=True)}]
	return []


#: Work-order tasks, by the kind of order each opens.
WORK_ORDER_KINDS = {"IWOS": "Structure", "IWOI": "Installation"}


def job_card(installation, task_code=None, order=None):
	"""The job a work order is for - customer, site, system, contractor, photographs - as its
	pages show it (templates/includes/portal_job_card.html); None for any other record."""
	is_order = order is not None and getattr(order, "doctype", None) == "Installation Work Order" and order.get("name")
	if not is_order and task_code not in WORK_ORDER_KINDS:
		return None
	from a3_sola.api import work_order_print

	kind = WORK_ORDER_KINDS.get(task_code) or (order.get("work_order_kind") if order else None)
	return work_order_print.job_context(installation, kind, work_order=order if is_order else None,
		contractor=order.get("solar_contractor") if order else None)


def task_form_groups(slug, values, first_label=None):
	"""The task's create form: the doctype's whole form, as its edit form lays it out, for a
	new document holding `values`, less the fixed fields - or only the task's own fields
	(TASK_FORM_FIELDS). A section that applies to other tasks only (an Installation Task's,
	by code) is hidden by its rule in the browser. The first section is `first_label` (the
	task's name), else the collection's title."""
	doc = frappe.new_doc(get_collection(slug)["doctype"])
	doc.update(values)
	only = TASK_FORM_FIELDS.get(values.get("task_code"))
	groups = []
	for g in edit_fields_for(doc, first_label or get_collection(slug)["title"]):
		sections = [
			{**s, "fields": [
				f for f in s["fields"]
				if f["fieldname"] not in TASK_FIXED and (only is None or f["fieldname"] in only)
			]} for s in g["sections"]
		]
		sections = [s for s in sections if s["fields"]]
		if sections:
			groups.append({**g, "sections": sections})
	for field, (label, on, _off) in TASK_FORM_CHECKS.get(values.get("task_code"), {}).items():
		for spec in (f for g in groups for s in g["sections"] for f in s["fields"] if f["fieldname"] == field):
			spec.update({"type": "Check", "label": label, "value": 1 if doc.get(field) == on else 0, "show_when": ""})
	can_claim = reimbursable(values.get("solar_installation"), values.get("task_code"))
	for field, choices in task_form_choices(values.get("task_code"), can_claim).items():
		for spec in (f for g in groups for s in g["sections"] for f in s["fields"] if f["fieldname"] == field):
			labels = [label for label, _set in choices]
			held = next((label for label, sets in choices if all(doc.get(k) == v for k, v in sets.items())), labels[0])
			spec.update({"type": "Select", "options": labels, "value": held, "default": held})
	if not can_claim:
		for g in groups:
			for s in g["sections"]:
				s["fields"] = [f for f in s["fields"] if f["fieldname"] not in REIMBURSEMENT_FIELDS]
	for field, rule in TASK_FORM_SHOW_WHEN.get(values.get("task_code"), {}).items():
		for spec in (f for g in groups for s in g["sections"] for f in s["fields"] if f["fieldname"] == field):
			spec["show_when"] = rule
	return doc, groups


def task_form_choices(task_code, can_claim):
	"""The task's TASK_FORM_CHOICES, less the reimbursement choice where it allows none."""
	return {
		field: tuple((label, sets) for label, sets in choices
			if can_claim or not any(sets.get(k) for k in REIMBURSEMENT_FIELDS))
		for field, choices in TASK_FORM_CHOICES.get(task_code, {}).items()
	}


def source_prefill(slug):
	"""(source doc, step, values) when the create page was reached from another record.

	The pairing must be one the chain declares, and the source is read with the caller's
	own permissions, so this cannot be used to read a record the person may not see. A task
	opened from the project board is the other way in: the job, with `task` naming the task.
	"""
	source_dt = (frappe.form_dict.get("source_dt") or "").strip()
	source_name = (frappe.form_dict.get("source") or "").strip()
	if not source_dt or not source_name:
		return None, None, {}
	if source_dt == "Solar Installation":
		values = task_source(slug, source_name, (frappe.form_dict.get("task") or "").strip())
		if values is None:
			return None, None, {}
		return frappe.get_doc("Solar Installation", source_name), None, values

	step = portal_chain.find_step(source_dt, slug)
	if not step:
		return None, None, {}
	if not frappe.db.exists(source_dt, source_name):
		return None, None, {}
	doc = frappe.get_doc(source_dt, source_name)
	doc.check_permission("read")
	values = portal_chain.mapped_values(step, doc)
	# A consumer or survey also takes what its lead knows, as it would once saved, so the
	# form shows it now rather than after the save.
	if step["doctype"] in ("Solar Consumer", "Site Survey") and (values.get("lead") or values.get("solar_consumer")):
		from a3_sola.api import record_links
		extra = record_links.prefill(step["doctype"], lead=values.get("lead"), solar_consumer=values.get("solar_consumer"))
		values = {**extra, **values}
	return doc, step, values


def new_context(context, slug):
	cfg = get_collection(slug)
	meta = frappe.get_meta(cfg["doctype"])
	source_doc, step, prefill = source_prefill(slug)
	for fieldname, method in (cfg.get("defaults") or {}).items():
		if not prefill.get(fieldname):
			prefill = {**prefill, fieldname: frappe.get_attr(method)()}
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
	for f in fields:
		if f["fieldname"] in cfg.get("required", ()):
			f["reqd"] = True
		if f["fieldname"] in cfg.get("no_weekend", ()):
			f["no_weekend"] = True
	# The record a create form is filled from is asked for first: the lead, then the consumer.
	first = ("lead", "solar_consumer")
	fields.sort(key=lambda f: first.index(f["fieldname"]) if f["fieldname"] in first else len(first))
	context.collection = {**cfg, "slug": slug}
	context.fields = fields
	context.item_table = item_table(slug, editable=True)
	context.unrenderable = [
		label for label in unrenderable
		if not context.item_table or label != context.item_table["label"]
	]
	# Built by a mapper (a sales order from its quotation): the items it carries across are
	# shown as they will be, not typed, so the notice that they are wanted does not apply.
	context.source_items = None
	if step and step.get("via") and source_doc:
		from a3_sola.api.portal_chain import mapped_doc

		mapped = mapped_doc(step, source_doc)
		currency = mapped.get("currency") or "INR"
		context.source_items = {
			"rows": [{"item": r.item_name or r.item_code, "description": frappe.utils.strip_html(r.description or ""),
				"qty": frappe.utils.flt(r.qty), "rate": frappe.utils.fmt_money(r.rate, currency=currency),
				"amount": frappe.utils.fmt_money(r.amount, currency=currency)} for r in mapped.get("items") or []],
			"total": frappe.utils.fmt_money(mapped.get("grand_total") or mapped.get("total"), currency=currency),
		}
		items_label = _(meta.get_label("items"))
		context.unrenderable = [label for label in context.unrenderable if label != items_label]
	# Carried on the form so the write endpoint can apply the rest of the mapping and
	# record the new document back on the record it came from.
	context.source_dt = source_doc.doctype if source_doc else ""
	context.source_name = source_doc.name if source_doc else ""
	context.source_task = (frappe.form_dict.get("task") or "").strip() if context.source_dt == "Solar Installation" else ""
	if context.source_task:
		# A task's document is created on its whole form, as it is edited, so every detail
		# the task asks for is there - not just the mandatory ones.
		from a3_sola.api.stages import _get_stage

		# Named for its task (Form 1 Generation), not for the kind of document it makes.
		context.task_name = _get_stage(source_doc, context.source_task).stage_name
		context.record, context.groups = task_form_groups(slug, prefill, context.task_name)
		# What the job already knows for a blank field (the section's Assistant Engineer).
		apply_prefill(context.record, context.groups)
		context.task_form = True
		context.fixed = [(k, prefill[k]) for k in TASK_FIXED if prefill.get(k)]
		context.endpoint = "a3_sola.api.portal_crud.create_record"
		context.view_route = context.source_route
		context.title = "New " + cfg["singular"]
		context.task_downloads = task_downloads(source_doc.name, context.source_task)
		context.task_missing = task_missing(source_doc.name, context.source_task)
		if context.source_task not in CLAIM_IN_FORM:
			context.claim = task_claim(source_doc.name, context.source_task)
		context.task_people = task_people(source_doc.name, context.source_task)
		context.job_card = job_card(source_doc, context.source_task, context.record)
		from a3_sola.api import structure_bom

		lists = structure_bom.MATERIAL_LISTS.get(context.source_task)
		if lists and context.record.get(lists[1]) and not context.record.get(lists[0]):
			structure_bom.fill_materials(context.record)
		context.item_table = item_table(slug, context.record, editable=True)
		# Choosing another BOM on the form refills the list (portal_structure_bom.html).
		context.bom_follow = lists[1] if lists else None
	context.source_title = record_title(source_doc) if source_doc else ""
	context.source_route = (
		record_route(SLUG_OF_DOCTYPE[source_doc.doctype], source_doc.name)
		if source_doc and source_doc.doctype in SLUG_OF_DOCTYPE else ""
	)
	if source_doc and source_doc.doctype == "Lead":
		context.source_route = "/a3solaportal/leads/{0}".format(frappe.utils.quote(source_doc.name))
	if context.get("task_form"):
		context.page_title = context.page_meta_title = context.task_name
		context.crumbs = [
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": context.source_title, "href": context.source_route},
			{"label": context.task_name},
		]
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
	"warranty-claims", "generation-readings", "reimbursements", "fee-recoveries", "installation-snags",
	"material-requests", "purchase-receipts", "stock-entries", "serial-numbers",
	"journal-entries", "additional-structures", "additional-cables", "special-discounts",
}

#: The documents a project's tasks are carried out in, by slug, as the board opens them.
#: Submitting one is what completes its task (tasks.sync_from_document). The purchase
#: order and delivery note are ERPNext's own forms and are worked in the desk.
TASK_SLUGS = {
	"installation-tasks", "fee-payments", "portal-applications", "loan-applications",
	"agreements", "work-orders", "dispatch-notices", "document-packs", "commissioning",
	"customer-reviews", "subsidy-claims",
}

#: The doctypes a project's tasks are done in, whose Assigned To is the task's lead person.
TASK_DOCTYPES_WITH_PEOPLE = {COLLECTIONS[s]["doctype"] for s in TASK_SLUGS}

#: Slugs whose record may be submitted from the portal: the sales order - submitting it is
#: the handoff into Operations, opening the Solar Installation, its document register and
#: its billing plan - and the task documents, so a task is completed where it is opened.
#: Not the agreement: its task is done when the stamp paper is bought, and submitting it is
#: executing the agreement, which needs its text generated first - a desk step. The CRM
#: steps before the order are submitted on the desk, as they always have been.
SUBMIT_SLUGS = {"sales-orders"} | (TASK_SLUGS - {"agreements"})

#: The submit button's words, by slug; "Submit" otherwise.
SUBMIT_LABELS = {"sales-orders": "Submit order", "installation-tasks": "Complete task"}

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


def edit_route(slug, name):
	"""Where a record is edited: a design estimate in its builder, where the system and the
	prices live; anything else in its edit form."""
	return record_route(slug, name) + ("/design" if slug == "design-estimates" else "/edit")


#: What a SUBMITTED record may still be changed in from the portal, by doctype - fields the
#: doctype allows on submit. A project is submitted when it is created; its finance can
#: change later (a loan taken or dropped), and the tasks follow (stages.reapply_applicability).
EDITABLE_AFTER_SUBMIT = {
	"Solar Installation": (
		"is_financed", "lender", "lender_branch", "bank_ifsc_code", "bank_account_holder_name",
		"bank_account_no", "loan_sanction_no", "jan_samarth_id",
		# The job's people: its tasks are assigned to them by position.
		"project_manager", "site_engineer", "sales_coordinator",
		# Its contractors: work orders, the dispatch notice and the certificate go to them.
		"structure_contractor", "electrical_contractor",
	),
	# What the bank's covering letter and feasibility report print, corrected before a reprint.
	"Loan Application": (
		"consumer_name", "installation_address", "district", "state", "pincode", "place",
		"national_portal_application_id", "discom_consumer_id", "discom_id", "jan_samarth_id",
		"loan_sanction_no", "feasibility_status", "capacity_applied_kw", "capacity_installable_kw",
		"project_cost_all_inclusive",
	),
}


def is_editable(doc):
	"""Whether the portal's edit form may be pointed at this record.

	Write permission is not the whole answer for a submittable doctype: a submitted
	Quotation or Sales Order is closed to `save`, so offering an Edit button on one would
	lead to a form that cannot be saved. A doctype that is not submittable sits at
	docstatus 0 for its whole life, so this is simply write permission for those.
	"""
	docstatus = frappe.utils.cint(doc.get("docstatus"))
	editable_state = docstatus == 0 or (docstatus == 1 and doc.doctype in EDITABLE_AFTER_SUBMIT)
	return bool(doc.has_permission("write")) and editable_state


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
	# A submitted record is closed, except the few fields its doctype lets change after
	# submit (EDITABLE_AFTER_SUBMIT) - the edit form then offers only those.
	docstatus = frappe.utils.cint(doc.get("docstatus"))
	if permtype == "write" and docstatus != 0 and not (docstatus == 1 and doctype in EDITABLE_AFTER_SUBMIT):
		frappe.throw(
			_("{0} has been submitted and can no longer be edited here.").format(name),
			frappe.PermissionError,
		)
	return doc


#: Who a record is for, in the order a person would name it: the consumer, else the lead,
#: else the customer. A record with no title of its own - a survey, an estimate, a check -
#: is shown under this name, the way the Lead and Consumer pages show theirs.
PERSON_DOCTYPES = ("Solar Consumer", "Lead", "Customer")


def person_link(meta):
	"""The Link field that names who the record is for, or None."""
	for doctype in PERSON_DOCTYPES:
		for df in meta.fields:
			if df.fieldtype == "Link" and df.options == doctype and not df.hidden:
				return df
	return None


def record_title(doc):
	"""What the record is called on the page: its title, else who it is for, else its id."""
	title_field = doc.meta.title_field
	title = doc.get(title_field) if title_field and title_field != "name" else None
	if not title:
		df = person_link(doc.meta)
		if df and doc.get(df.fieldname):
			title = link_title(df.options, doc.get(df.fieldname))
	return title or doc.name


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
				section = {"label": df.label or "", "fields": [], "depends_on": df.depends_on or ""}
				group["sections"].append(section)
			continue
		if df.fieldtype == "Column Break":
			continue
		if df.hidden or df.fieldtype not in DISPLAY_TYPES_ALL:
			continue
		if section is None:
			section = {"label": "", "fields": [], "depends_on": ""}
			group["sections"].append(section)
		section["fields"].append(df)

	for g in groups:
		g["sections"] = [s for s in g["sections"] if s["fields"]]
	return [g for g in groups if g["sections"]]


from a3_sola.api.portal_fields import (  # noqa: E402  - grouped with the code that uses it
	DISPLAY_TYPES as DISPLAY_TYPES_ALL, INPUT_TYPES as INPUT_TYPES_ALL, detail_row, edit_spec,
	is_portal_file, link_choices, link_title,
	DEPENDENT_ALSO, DEPENDENT_LINKS, default_for, link_filters,
)


def _backlink_field(doctype, target):
	"""The Link field on `doctype` that points at `target`, or None."""
	for df in frappe.get_meta(doctype).get_link_fields():
		if df.options == target:
			return df.fieldname
	return None


def assigned_count(doc):
	"""How many people the record is assigned to now - its open assignments (ToDo)."""
	return len(set(frappe.get_all("ToDo", filters={"reference_type": doc.doctype, "reference_name": doc.name,
		"status": "Open"}, pluck="allocated_to")))


def attachment_count(doc):
	"""How many files are attached to the record."""
	return frappe.db.count("File", {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_folder": 0})


def people_and_files_tiles(doc):
	"""The two counts every record page shows: who it is assigned to, and what is attached."""
	return [
		{"value": assigned_count(doc), "label": "Assigned", "icon": "user", "tone": "green"},
		{"value": attachment_count(doc), "label": "Attachments", "icon": "doc", "tone": "amber"},
	]


def record_snapshot(slug, doc):
	"""Tiles for the snapshot card: who it is assigned to, its attachments, linked records,
	plus age."""
	tiles = people_and_files_tiles(doc)
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
			rows = [detail_row(df, doc.get(df.fieldname)) for df in s["fields"]
			        if df.fieldname not in PORTAL_HIDDEN.get(doc.doctype, ())]
			if rows:
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
	context.edit_route = edit_route(slug, doc.name)
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
	context.submit_label = SUBMIT_LABELS.get(slug, "Submit")
	if doc.doctype == "Site Survey":
		# The survey as the team's paper Site Survey Report, to view or download.
		from a3_sola.api import survey_print

		context.print_buttons = [
			{"label": "View Site Survey Report", "url": survey_print.url(doc.name), "icon": "eye"},
			{"label": "Download Site Survey Report", "url": survey_print.url(doc.name, download=True), "icon": "download"},
		]
		context.head_actions_template = context.get("head_actions_template") or "templates/includes/portal_print_buttons.html"
	# A task's document is reached from its project's board, and leads back there.
	if slug in TASK_SLUGS and doc.get("solar_installation"):
		context.back_link = {"href": record_route("projects", doc.solar_installation), "label": "Back to project"}
		context.claim = task_claim(doc.solar_installation, tasks_code_for(doc))
		context.task_people = task_people(doc.solar_installation, tasks_code_for(doc))
		context.task_downloads = task_downloads(doc.solar_installation, tasks_code_for(doc), doc.name)
		context.task_missing = task_missing(doc.solar_installation, tasks_code_for(doc))
		from a3_sola.api import portal_share

		if doc.doctype == "Installation Work Order":
			# The job for the contractor, and its PDF to view, download and send to them.
			from a3_sola.api import work_order_print

			context.job_card = job_card(doc.solar_installation, None, doc)
			if not context.get("head_actions_template"):
				context.share = portal_share.share_links(doc, work_order_print.url(doc.name))
				context.head_actions_template = "templates/includes/portal_share.html"
		if portal_share._is_purchase_list(doc) and not context.get("head_actions_template"):
			# The purchase list to view, download, and send to the supplier by WhatsApp or email.
			from a3_sola.api import purchase_list

			context.share = portal_share.share_links(doc, purchase_list.url(doc.name))
			context.pending_card = pending_card(doc, can_tick=True)
			# What the supplier could not give, once marked: its own list for the next supplier.
			pending = purchase_list.pending_rows(doc)
			if pending:
				context.share_pending = portal_share.share_links(doc, purchase_list.url(doc.name, pending=True),
					part=portal_share.PENDING)
				context.share_pending["count"] = len(pending)
			context.head_actions_template = "templates/includes/portal_purchase_share.html"
		if context.task_downloads and not context.get("head_actions_template"):
			context.head_actions_template = "templates/includes/portal_task_downloads.html"

		# A task's people are its own (the strip in the head); the to-do card would be a second list.
		context.hide_assignment = bool(context.task_people)
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


#: Show-when rules the portal's edit form adds to a doctype's own, as {doctype: {field: rule}}.
#: The consumer's external identifiers belong with the subsidy history on the portal; the
#: desk keeps showing them.
PORTAL_SHOW_WHEN = {
	"Solar Consumer": {
		"discom_id": "has_availed_prior_subsidy",
		"national_portal_consumer_id": "has_availed_prior_subsidy",
	},
}

#: Values the edit form offers for blank fields, as {doctype: fn(doc) -> (where from, {field: value})}.
#: Only offered: the box is filled in the browser when the field shows, and nothing is
#: written until it is saved. A project's loan is usually with the consumer's own bank;
#: when it is not, the person overtypes it, and the consumer's record keeps its own details.
def _section_engineer(doc):
	"""Form 2 and Form 3: the Assistant Engineer and phone the job's section has on record."""
	section = frappe.db.get_value("Solar Installation", doc.get("solar_installation"), "discom_section") \
		if doc.get("solar_installation") else None
	if not section or doc.get("pack_type") not in ("KSEB Form 2", "KSEB Form 3"):
		return "DISCOM Section", {}
	ae = frappe.db.get_value("DISCOM Section", section,
		["assistant_engineer_name", "assistant_engineer_phone"], as_dict=True) or frappe._dict()
	return "DISCOM Section", {"ae_name": ae.assistant_engineer_name, "ae_phone": ae.assistant_engineer_phone}


PORTAL_PREFILL = {
	"Document Pack": _section_engineer,
	"Solar Installation": lambda doc: (
		"Solar Consumer", installation_lead.consumer_bank(doc.solar_consumer, doc.lender)
	),
	"Solar Consumer": lambda doc: ("customer name", {"bank_account_holder_name": doc.consumer_name}),
}

#: Fields that follow another while they still match it, as {doctype: {field: source}}: the
#: account holder is the consumer until somebody says otherwise, so renaming the consumer
#: renames an untouched holder too.
PORTAL_FOLLOWS = {
	"Solar Consumer": {"bank_account_holder_name": "consumer_name"},
}

#: Totals the form adds up as their parts are typed, as {doctype: {field: (parts)}}. Still
#: editable: one typed over stops following, as the server keeps it (Site Survey).
from a3_sola.solar_crm.doctype.site_survey.site_survey import CABLE_TOTALS  # noqa: E402

PORTAL_SUMS = {
	"Site Survey": CABLE_TOTALS,
}


def edit_fields_for(doc, first_label=None):
	"""The fields the edit form renders, grouped like the form, with current values.

	Reused verbatim by the update endpoint as its allow-list, so the two never drift: a
	field the form does not render is a field the endpoint refuses to set.
	"""
	# A submitted record offers only what it may still change.
	only = EDITABLE_AFTER_SUBMIT.get(doc.doctype) if frappe.utils.cint(doc.get("docstatus")) == 1 else None
	if frappe.utils.cint(doc.get("docstatus")) == 1 and only is None:
		return []
	groups = []
	for g in form_groups(doc.meta, first_label):
		sections = []
		for s in g["sections"]:
			specs = []
			for df in s["fields"]:
				if ((df.fieldtype not in INPUT_TYPES_ALL and not is_portal_file(doc.doctype, df))
						or df.read_only or df.fieldname in AUTO_FIELDS
						or df.fieldname in PORTAL_HIDDEN.get(doc.doctype, ())
						# A task's document: its people are the task's, in the Assigned to strip.
						or (df.fieldname == "assigned_to" and doc.doctype in TASK_DOCTYPES_WITH_PEOPLE)
						or (only is not None and df.fieldname not in only)):
					continue
				spec = edit_spec(df, doc.get(df.fieldname), doc)
				# Shown only with the answer it belongs to, as the desk's depends_on does - the
				# field's own rule, else its section's.
				spec["show_when"] = (
					PORTAL_SHOW_WHEN.get(doc.doctype, {}).get(df.fieldname) or show_when_expr(df)
					or section_show_when(s.get("depends_on"))
				)
				specs.append(spec)
			if specs:
				sections.append({"label": s["label"] if s["label"] != g["label"] or len(g["sections"]) > 1 else "", "fields": specs})
		if sections:
			groups.append({"key": g["key"], "label": g["label"], "sections": sections})
	return groups


def apply_prefill(doc, groups):
	"""Mark each blank field in `groups` with the value it is offered (PORTAL_PREFILL), and
	each field that follows another (PORTAL_FOLLOWS) or adds others up (PORTAL_SUMS).

	A value the record already has is never replaced. Kept off `edit_fields_for`, which is
	also the save allow-list and has no use for the lookup.
	"""
	rule = PORTAL_PREFILL.get(doc.doctype)
	follows = PORTAL_FOLLOWS.get(doc.doctype, {})
	sums = PORTAL_SUMS.get(doc.doctype, {})
	if not (rule or follows or sums):
		return groups
	source, values = rule(doc) if rule else ("", {})
	for g in groups:
		for s in g["sections"]:
			for spec in s["fields"]:
				value = values.get(spec["fieldname"])
				if value and spec["value"] in ("", None):
					spec["prefill"] = value
					spec["prefill_from"] = source
				if spec["fieldname"] in follows:
					spec["follows"] = follows[spec["fieldname"]]
				if spec["fieldname"] in sums:
					spec["sum_of"] = ",".join(sums[spec["fieldname"]])
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
	context.groups = apply_prefill(doc, edit_fields_for(doc, cfg["title"]))
	if doc.doctype == "Installation Task":
		from a3_sola.api.structure_bom import MATERIAL_LISTS

		context.bom_follow = (MATERIAL_LISTS.get(doc.get("task_code")) or (None, None))[1]
	context.view_route = record_route(slug, doc.name)
	context.back_link = {"href": context.view_route, "label": "Back to " + cfg["singular"]}
	context.endpoint = "a3_sola.api.portal_crud.update_record"
	context.item_table = item_table(slug, doc, editable=True)
	if doc.doctype == "Installation Work Order":
		context.job_card = job_card(doc.solar_installation, None, doc)
	if doc.doctype == "Installation Task" and doc.get("task_code") in ("SPROC", "PROC"):
		context.pending_card = pending_card(doc, can_tick=False)
	context.update(_record_about(doc))
	# The POST is an unsafe method on an authenticated session, so it needs a CSRF token.
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


def pending_card(doc, can_tick=True):
	"""A procurement task's Pending Items card (portal_pending_items.html): the items awaited
	first, then the received ones as the record. Ticked on the task's page while it is open."""
	from frappe.utils import flt, format_date

	rows = sorted(doc.get("pending_items") or [], key=lambda r: (bool(r.received), r.idx))
	open_ = len([r for r in rows if not r.received])
	tick = can_tick and doc.docstatus == 0 and bool(doc.has_permission("write"))
	return {
		"task": doc.name, "open": open_, "can_tick": tick,
		"note": "" if can_tick else "Tick items Received on the task's page, after saving the list.",
		"rows": [{"row": r.name, "material": r.material, "qty": "{0:g}".format(flt(r.qty)), "uom": r.uom,
			"marked_on": format_date(r.marked_on, "d MMM yyyy") if r.marked_on else "", "supplier": r.supplier,
			"received": bool(r.received), "received_on": format_date(r.received_on, "d MMM") if r.received_on else ""}
			for r in rows],
	}


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
	A collection whose grid depends on the record (`item_table_by`: field, {value: table})
	shows the record's table, and none for a record without one.
	"""
	cfg = get_collection(slug)
	fieldname = cfg.get("item_table")
	by = cfg.get("item_table_by")
	if by:
		fieldname = by[1].get(doc.get(by[0])) if doc is not None else None
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
		"total": frappe.format_value(total, parent.get_field("total_amount"), doc) if doc and parent.has_field("total_amount") else "",
		"show_total": cfg.get("item_total", True),
	}
	# What the grid's script starts from, embedded in a <script> tag: "</" is escaped so a
	# row's text can never close that tag.
	spec["json"] = frappe.as_json({k: spec[k] for k in ("columns", "rows", "rule")}).replace("</", "<\\/")
	return spec


def item_rows(slug, posted, doc=None):
	"""The posted rows, kept to the grid's editable columns: the browser sets nothing else.

	`posted` is the JSON the grid carries in its hidden `__items` input. Blank rows are
	dropped so an untouched last line does not fail validation.
	"""
	spec = item_table(slug, doc)
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


def section_show_when(depends_on):
	"""A section's `depends_on` as a show-when rule for each of its fields, or "".

	The shapes a field's own rule takes (show_when_expr), and `eval:["a","b"].includes(doc.field)`,
	written "field=a|b" - an Installation Task's sections, one per task code.
	"""
	expr = (depends_on or "").strip()
	rule = show_when_expr(frappe._dict(depends_on=expr))
	if rule:
		return rule
	match = re.match(r"^eval:\[(.*)\]\.includes\(doc\.([a-z0-9_]+)\)$", expr)
	if not match:
		return ""
	values = re.findall(r"[\"']([^\"']*)[\"']", match.group(1))
	return "{0}={1}".format(match.group(2), "|".join(values)) if values else ""


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
