# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A sales order is one submitted quotation, ordered.

The person picks the lead, then one of its quotations - choosing one is required. The
order is ERPNext's own mapping of that quotation (quotation.make_sales_order): its
customer, its package line at the quoted price, its terms. The page asks only what the
quotation cannot say - the order date and the delivery date - and shows the rest in three
tabs, as the quotation page does: the order details, the bill of materials, the terms.
"""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, flt, format_date, getdate, today

from a3_sola.api import quotation_option

SLUG = "sales-orders"
#: What the page asks of an order; everything else is the quotation's.
ASKED = ("transaction_date", "delivery_date")
QUOTE_FIELDS = ["name", "docstatus", "status", "transaction_date", "valid_till", "solar_design_estimate", "solar_consumer",
	"solar_proposal", "selected_option", "quotation_to", "party_name", "customer_name", "rounded_total", "grand_total", "currency"]


def route_of(name):
	return "/a3solaportal/{0}/{1}".format(SLUG, frappe.utils.quote(name))


# ------------------------------------------------------------------ who and which quotation
def lead_of(quotation):
	"""The lead a quotation was raised for: its design estimate's, else its consumer's, else
	the lead it is still addressed to."""
	q = quotation
	if isinstance(q, str):
		q = frappe.db.get_value("Quotation", q, QUOTE_FIELDS, as_dict=True)
	if not q:
		return None
	lead = frappe.db.get_value("Solar Design Estimate", q.solar_design_estimate, "lead") if q.get("solar_design_estimate") else None
	if not lead and q.get("solar_consumer"):
		lead = frappe.db.get_value("Solar Consumer", q.solar_consumer, "lead")
	if not lead and q.get("quotation_to") == "Lead":
		lead = q.party_name
	return lead or None


def lead_quotations(lead):
	"""The lead's quotations the caller may read, newest first; cancelled ones are gone."""
	estimates = frappe.get_all("Solar Design Estimate", filters={"lead": lead}, pluck="name")
	consumers = frappe.get_all("Solar Consumer", filters={"lead": lead}, pluck="name")
	or_filters = [["party_name", "=", lead]]
	if estimates:
		or_filters.append(["solar_design_estimate", "in", estimates])
	if consumers:
		or_filters.append(["solar_consumer", "in", consumers])
	rows = frappe.get_list("Quotation", filters={"docstatus": ["<", 2]}, or_filters=or_filters, fields=QUOTE_FIELDS,
		order_by="creation desc", limit_page_length=0)
	return [r for r in rows if lead_of(r) == lead]


def lead_choices(also=None):
	"""The leads an order can be raised for: those with a quotation on file."""
	from a3_sola.api.portal_fields import link_title

	rows = frappe.get_list("Quotation", filters={"docstatus": ["<", 2]}, fields=QUOTE_FIELDS, limit_page_length=0)
	leads = ({lead_of(r) for r in rows} | {also}) - {None, ""}
	return [{"value": lead, "label": link_title("Lead", lead)} for lead in sorted(leads) if frappe.db.exists("Lead", lead)]


def current_quotation(order):
	"""The quotation an order was raised from - ERPNext records it on the order's item rows."""
	doc = frappe.get_doc("Sales Order", order) if isinstance(order, str) else order
	return next((r.prevdoc_docname for r in doc.get("items") or [] if r.get("prevdoc_docname")), None)


def orders_of(quotation, but=None):
	"""The sales orders, draft or submitted, raised from `quotation` - other than `but`."""
	return sorted(set(frappe.get_all("Sales Order Item",
		filters={"prevdoc_docname": quotation, "docstatus": ["<", 2], "parent": ["!=", but or ""]}, pluck="parent")))


def why_not(q, order=None):
	"""Why the quotation cannot be ordered (by `order`), or "" when it can."""
	if cint(q.docstatus) == 0:
		return _("Draft: submit it first")
	if q.status == "Lost":
		return _("Lost")
	ordered = orders_of(q.name, but=order)
	if ordered:
		return _("Ordered as {0}").format(", ".join(ordered))
	if q.valid_till and not cint(frappe.db.get_single_value("Selling Settings", "allow_sales_order_creation_for_expired_quotation")) \
			and getdate(q.valid_till) < getdate(today()):
		return _("Validity ended on {0}").format(format_date(q.valid_till))
	return ""


def _card(q, order=None):
	"""A quotation as the page's card shows it."""
	opt = quotation_option._option(q.solar_design_estimate, 0) if q.get("solar_design_estimate") else None
	total = flt(q.rounded_total or q.grand_total)
	reason = why_not(q, order)
	return {
		"quotation": q.name, "date": format_date(q.transaction_date) if q.transaction_date else "", "status": q.status,
		"draft": cint(q.docstatus) == 0, "option": q.selected_option or "", "proposal": q.solar_proposal or "",
		"estimate": q.solar_design_estimate or "", "customer": q.customer_name or q.party_name or "",
		"package": (opt or {}).get("package") or "", "capacity_kwp": (opt or {}).get("capacity_kwp") or 0,
		"connection_type": (opt or {}).get("connection_type") or "", "system_type": (opt or {}).get("system_type") or "",
		"total": total, "total_text": frappe.utils.fmt_money(total, currency=q.currency or "INR"),
		"orderable": not reason, "reason": reason, "route": "/a3solaportal/quotations/" + frappe.utils.quote(q.name),
	}


@frappe.whitelist()
def quotations(lead=None, order=None):
	"""The quotations an order can be raised from: the lead's, each said orderable or why not.
	An existing order's own quotation is always among them."""
	own = None
	if order:
		frappe.has_permission("Sales Order", "read", order, throw=True)
		own = current_quotation(order)
	rows = []
	if lead:
		frappe.has_permission("Lead", "read", lead, throw=True)
		rows = lead_quotations(lead)
	if own and own not in {r.name for r in rows} and frappe.has_permission("Quotation", "read", own):
		rows.append(frappe.db.get_value("Quotation", own, QUOTE_FIELDS, as_dict=True))
	return [_card(r, order) for r in rows]


# ------------------------------------------------------------------ what the tabs show
@frappe.whitelist()
def quotation_view(quotation, order=None):
	"""The three tabs - order details, bill of materials, terms - and the pop-up's preview
	for a quotation, read with the caller's own permissions."""
	frappe.has_permission("Quotation", "read", quotation, throw=True)
	so = None
	if order:
		frappe.has_permission("Sales Order", "read", order, throw=True)
		so = frappe.get_doc("Sales Order", order)
		if current_quotation(so) != quotation:
			so = None  # the order is being pointed at another quotation: show that one's figures
	return render(frappe.get_doc("Quotation", quotation), so)


def render(q, order=None):
	"""Details (who, what and the order value), the BOM and the terms of the quotation's
	design option, as the quotation page shows them; the order's own figures once it has them."""
	estimate = q.get("solar_design_estimate")
	ctx = quotation_option.option_context(estimate, q.get("solar_proposal"), q) \
		if estimate and frappe.db.exists("Solar Design Estimate", estimate) else None
	option = "a3_sola/templates/includes/quotation_option.html"
	head = {
		"q": q, "order": order, "opt": (ctx or {}).get("opt"), "loan": (ctx or {}).get("loan"),
		"figures": quotation_option.quotation_price(order or q),
		"lead": lead_of(q), "solar": bool(q.get("solar_package")),
	}
	page = "a3_sola/templates/includes/sales_order_option.html"
	out = {"details": frappe.render_template(page, dict(head, part="details"))
		+ (frappe.render_template(option, dict(ctx, part="details", opt=None)) if ctx else "")}
	out["preview"] = frappe.render_template(page, dict(head, part="preview")) \
		+ (frappe.render_template(option, dict(ctx, part="preview", opt=None)) if ctx else "")
	for part in ("bom", "terms"):
		out[part] = frappe.render_template(option, dict(ctx, part=part)) if ctx \
			else frappe.render_template(page, dict(head, part=part))
	return out


# ------------------------------------------------------------------ save
@frappe.whitelist()
def save_order(quotation=None, values=None, name=None):
	"""Raise the order from the chosen quotation, or save a draft's dates or point it at
	another quotation; return its page. ERPNext maps the quotation (make_sales_order), so
	the customer, items, prices and terms are the quotation's."""
	values = frappe.parse_json(values) or {}
	if not quotation:
		frappe.throw(_("Choose the quotation this order is for."), frappe.MandatoryError, title=_("No Quotation Chosen"))
	frappe.has_permission("Quotation", "read", quotation, throw=True)
	doc = None
	if name:
		doc = frappe.get_doc("Sales Order", name)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("{0} is submitted: amend it in ERPNext to change it.").format(name), frappe.ValidationError)
	else:
		frappe.has_permission("Sales Order", "create", throw=True)

	if not doc or current_quotation(doc) != quotation:
		q = frappe.db.get_value("Quotation", quotation, QUOTE_FIELDS, as_dict=True)
		reason = why_not(q, name)
		if reason:
			frappe.throw(_("{0} cannot be ordered ({1}).").format(quotation, reason), title=_("Choose Another Quotation"))
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		mapped = make_sales_order(quotation)
		if not mapped.get("items"):
			frappe.throw(_("Everything on {0} is already ordered.").format(quotation))
		doc = _take_over(doc, mapped) if doc else mapped

	for field in ASKED:
		if field in values:
			doc.set(field, values.get(field) or None)
	doc.transaction_date = doc.transaction_date or today()
	if not doc.delivery_date:
		frappe.throw(_("Choose the delivery date."), frappe.MandatoryError, title=_("Delivery Date Missing"))
	# One delivery date for the order: the package line is delivered with it.
	for row in doc.items:
		row.delivery_date = doc.delivery_date
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return {"name": doc.name, "route": route_of(doc.name)}


#: An order's own fields, kept when a draft is pointed at another quotation.
KEPT = {"name", "naming_series", "transaction_date", "delivery_date", "owner", "creation", "modified", "modified_by",
	"docstatus", "idx", "amended_from"}


def _take_over(doc, mapped):
	"""A draft order made over from another quotation's mapping, keeping its own name and dates."""
	for df in mapped.meta.fields:
		if df.fieldname in KEPT or (df.fieldtype in no_value_fields and df.fieldtype not in table_fields):
			continue
		if df.fieldtype in table_fields:
			doc.set(df.fieldname, [])
			for row in mapped.get(df.fieldname) or []:
				doc.append(df.fieldname, row.as_dict(no_default_fields=True, no_child_table_fields=True))
		else:
			doc.set(df.fieldname, mapped.get(df.fieldname))
	return doc


# ------------------------------------------------------------------ the portal page
def page_context(context, name=None):
	"""Context for /a3solaportal/sales-orders/new and /a3solaportal/sales-orders/<name>."""
	from a3_sola.overrides.sales_order import default_delivery_date
	from a3_sola.www.a3solaportal import fill_shell

	doc = None
	if name:
		if not frappe.db.exists("Sales Order", name):
			raise frappe.DoesNotExistError(_("That sales order does not exist."))
		doc = frappe.get_doc("Sales Order", name)
		doc.check_permission("read")
	else:
		frappe.has_permission("Sales Order", "create", throw=True)
	crumbs = [{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Sales Order", "href": "/a3solaportal/" + SLUG},
		{"label": name or "New"}]
	fill_shell(context, active_route="/a3solaportal/" + SLUG, page_title=name or _("New sales order"), crumbs=crumbs)

	lead, quotation = "", ""
	if doc:
		quotation = current_quotation(doc) or ""
		lead = (lead_of(quotation) if quotation else None) or ""
		order_aside(context, doc)
	else:
		form = frappe.form_dict
		source_dt, source = (form.get("source_dt") or "").strip(), (form.get("source") or "").strip()
		if source_dt == "Quotation" and source and frappe.db.exists("Quotation", source) \
				and frappe.has_permission("Quotation", "read", source):
			quotation = source
			lead = lead_of(source) or ""
		elif source_dt == "Lead":
			lead = source
		lead = lead or (form.get("lead") or "").strip()
	editable = (not doc) or (cint(doc.docstatus) == 0 and bool(doc.has_permission("write")))

	context.order = doc
	context.order_name = name or ""
	context.title = name or _("New sales order")
	context.editable = editable
	context.submitted = bool(doc and cint(doc.docstatus) == 1)
	context.values = {
		"transaction_date": str(doc.transaction_date) if doc and doc.transaction_date else today(),
		"delivery_date": str(doc.delivery_date or "") if doc else default_delivery_date(),
	}
	context.lead_choices = lead_choices(lead)
	context.state_json = frappe.as_json({"lead": lead, "quotation": quotation, "name": name or "", "editable": editable,
		"docstatus": cint(doc.docstatus) if doc else 0, "status": doc.status if doc else ""})
	context.desk_route = "/app/sales-order/" + frappe.utils.quote(name) if name else ""
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


def order_aside(context, doc):
	"""Attachments, snapshot, at a glance and next steps: the boxes every record in the chain carries."""
	from a3_sola.api import portal_chain
	from a3_sola.www.a3solaportal.collections import is_editable, record_glance, record_snapshot

	context.tiles = record_snapshot(SLUG, doc)
	context.glance = record_glance(doc)
	context.chain_steps = portal_chain.steps_for(doc)
	context.record_doctype = doc.doctype
	context.record_name = doc.name
	context.can_write = is_editable(doc)
	return context
