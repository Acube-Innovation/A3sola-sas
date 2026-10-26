# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A quotation is one option of a proposal, as the proposal finalised it.

The person picks the lead (or the proposal) and one of its options - a design estimate.
Everything else is the option's: the customer and site, the bill of materials, the price,
the terms. It is shown, not typed - the same details the proposal print sets out - and
the Quotation carries it as one package line priced at the option's plant total, with the
option's Special Discount as the discount and the company's default GST. `apply_option`
(Quotation before_validate) holds that line to the option however the quotation is saved,
on the desk or the portal.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, today

from a3_sola.api.print_cover import (
	CHARGES, PLANT_LINES, print_components, print_rest, print_summary, plant_description,
)


# ------------------------------------------------------------------ the options on offer
@frappe.whitelist()
def options(lead=None, proposal=None):
	"""The options a quotation can be raised for: each proposal of the lead (or the one
	proposal given), with its design estimates in order - Option 1 is the base. A lead's
	estimate that is in no proposal is offered on its own, draft or submitted, as a proposal's
	drafts are - the portal has no way to submit an estimate, so a new one would otherwise
	never reach the quotation until it was put in a proposal."""
	if proposal:
		lead = lead or frappe.db.get_value("Solar Proposal", proposal, "lead")
	if not lead:
		return {"proposals": [], "loose": []}
	frappe.has_permission("Lead", "read", lead, throw=True)
	filters = {"lead": lead, "docstatus": ["<", 2]}
	if proposal:
		filters["name"] = proposal
	proposals, offered = [], set()
	for p in frappe.get_all("Solar Proposal", filters=filters, fields=["name", "status", "proposal_date", "current_version"],
			order_by="creation desc"):
		rows = frappe.get_all("Solar Proposal Estimate", filters={"parent": p.name, "parenttype": "Solar Proposal"},
			fields=["solar_design_estimate"], order_by="idx asc")
		opts = [_option(r.solar_design_estimate, i) for i, r in enumerate(rows, 1)]
		offered.update(r.solar_design_estimate for r in rows)
		proposals.append({"name": p.name, "status": p.status, "version": cint(p.current_version),
			"date": frappe.utils.format_date(p.proposal_date) if p.proposal_date else "", "options": [o for o in opts if o]})
	loose = [] if proposal else [
		o for o in (_option(n, 0) for n in frappe.get_all("Solar Design Estimate",
			filters={"lead": lead, "docstatus": ["<", 2]}, pluck="name", order_by="creation asc") if n not in offered) if o
	]
	return {"proposals": proposals, "loose": loose}


def _option(estimate, number):
	if not estimate or not frappe.db.exists("Solar Design Estimate", estimate):
		return None
	est = frappe.get_doc("Solar Design Estimate", estimate)
	return {
		"estimate": est.name, "number": number, "submitted": est.docstatus == 1,
		"package": frappe.db.get_value("Solar Package", est.solar_package, "package_name") if est.solar_package else "",
		"system_type": est.system_type or "", "connection_type": est.connection_type or "",
		"capacity_kwp": round(sum(flt(r.total_capacity_kwp) for r in est.panels if not r.is_option), 2),
		"price": flt(plant_amount(est)), "price_text": frappe.utils.fmt_money(plant_amount(est), currency="INR"),
	}


# ------------------------------------------------------------------ the price
def plant_amount(est):
	"""What the quotation's one line charges: the plant, and the extra structure and cable
	raised against the estimate. KSEB fees are a reimbursement and stay out of it; the
	Special Discount is the quotation's discount, not a lower rate."""
	lines = {line["key"]: flt(line["amount"]) for line in est.commercials()["lines"]}
	plant = sum(lines.get(k, 0) for k in PLANT_LINES)
	for doctype, sign in CHARGES:
		if sign > 0:
			plant += _charge_total(doctype, est.name)
	return flt(plant, 2)


def special_discount(est):
	return _charge_total("Special Discount", est.name)


def _charge_total(doctype, estimate):
	names = frappe.get_all(doctype, filters={"solar_design_estimate": estimate, "docstatus": ["<", 2]}, pluck="name")
	return sum(flt(frappe.db.get_value(doctype, n, "total_amount")) for n in names)


# ------------------------------------------------------------------ what the tabs show
def option_doc(estimate, proposal=None, quotation=None):
	"""A proposal-shaped record of one option, for the print helpers: the proposal's own
	customer and site details where there is one, the option as its only estimate."""
	est = frappe.get_doc("Solar Design Estimate", estimate)
	base = frappe.get_doc("Solar Proposal", proposal).as_dict() if proposal and frappe.db.exists("Solar Proposal", proposal) else {}
	consumer = frappe.db.get_value("Solar Consumer", est.solar_consumer,
		["consumer_name", "mobile_no", "email_id", "village", "local_body_name", "taluk"], as_dict=True) if est.solar_consumer else {}
	doc = frappe._dict(base)
	doc.update({
		"doctype": "Solar Proposal", "solar_design_estimate": est.name,
		"design_estimates": [frappe._dict(solar_design_estimate=est.name)],
		"lead": doc.get("lead") or est.lead, "solar_consumer": doc.get("solar_consumer") or est.solar_consumer,
		"site_survey": doc.get("site_survey") or est.site_survey, "company": doc.get("company") or est.company,
		"customer_name": doc.get("customer_name") or (consumer or {}).get("consumer_name"),
		"location": doc.get("location") or (consumer or {}).get("village") or (consumer or {}).get("local_body_name"),
		"district": doc.get("district") or (consumer or {}).get("taluk"),
		"proposal_date": doc.get("proposal_date") or today(),
	})
	if quotation:
		doc.update({"name": quotation.name, "proposal_date": quotation.transaction_date, "quotation": quotation})
	return doc


def render(estimate, proposal=None, quotation=None):
	"""The three tabs' HTML for one option: details, bill of materials (with the price), terms."""
	doc = option_doc(estimate, proposal, quotation)
	# The lead's loan answer, as the quotation carries it (Loan Required, read-only).
	if quotation:
		loan = "Yes" if quotation.get("is_financed") else "No"
	else:
		lead = frappe.db.get_value("Solar Design Estimate", estimate, "lead")
		loan = (frappe.db.get_value("Lead", lead, "loan_required") if lead else None) or "Not stated"
	ctx = {
		"opt": _option(estimate, 0), "proposal": proposal, "summary": print_summary(doc), "loan": loan,
		"components": print_components(doc), "rest": print_rest(doc),
		"quote": quotation_price(quotation) if quotation else None,
		"money": lambda v: frappe.utils.fmt_money(flt(v), currency="INR"),
	}
	out = {}
	for part in ("details", "bom", "terms", "preview"):
		out[part] = frappe.render_template("a3_sola/templates/includes/quotation_option.html", dict(ctx, part=part))
	return out


@frappe.whitelist()
def option_view(estimate, proposal=None, quotation=None):
	"""The tabs for an option, read with the caller's own permissions."""
	frappe.has_permission("Solar Design Estimate", "read", estimate, throw=True)
	q = frappe.get_doc("Quotation", quotation) if quotation and frappe.db.exists("Quotation", quotation) else None
	return render(estimate, proposal, q)


def quotation_price(q):
	"""The quotation's own figures, as it charges them: lines, discount, taxes, totals."""
	return {
		"lines": [{"description": frappe.utils.strip_html(r.description or r.item_name or ""), "amount": flt(r.amount)} for r in q.items],
		"total": flt(q.total), "discount": flt(q.discount_amount), "net_total": flt(q.net_total),
		"taxes": [{"description": t.description, "amount": flt(t.tax_amount)} for t in q.taxes if flt(t.tax_amount)],
		"grand_total": flt(q.rounded_total or q.grand_total),
	}


# ------------------------------------------------------------------ the quotation
def option_values(estimate, proposal=None):
	"""What a quotation for this option says on its head: who it is for and the links."""
	est = frappe.get_doc("Solar Design Estimate", estimate)
	customer = frappe.db.get_value("Solar Consumer", est.solar_consumer, "customer") if est.solar_consumer else None
	if not proposal:
		proposal = frappe.db.get_value("Solar Proposal Estimate", {"solar_design_estimate": est.name, "parenttype": "Solar Proposal",
			"docstatus": ["<", 2]}, "parent")
	recommended = next((o.option_name for o in est.options if o.is_recommended), None) or (est.options[0].option_name if est.options else None)
	# The option's own check, else the consumer's latest: eligibility is the customer's, and
	# the proposal checked it once, on its base option.
	check = frappe.db.get_value("Subsidy Eligibility Check", {"design_estimate": est.name, "docstatus": 1}, "name", order_by="creation desc") \
		or (frappe.db.get_value("Subsidy Eligibility Check", {"solar_consumer": est.solar_consumer, "docstatus": 1}, "name",
			order_by="creation desc") if est.solar_consumer else None)
	return {
		"quotation_to": "Customer" if customer else "Lead", "party_name": customer or est.lead,
		"solar_consumer": est.solar_consumer, "solar_design_estimate": est.name, "solar_proposal": proposal,
		"selected_option": recommended, "subsidy_eligibility_check": check, "solar_package": est.solar_package,
	}


@frappe.whitelist()
def save_quotation(estimate, proposal=None, name=None):
	"""Raise the quotation for an option, or point a draft at another option, and return it."""
	from a3_sola.api import cost_estimate
	from a3_sola.api.settings import get_value

	frappe.has_permission("Solar Design Estimate", "read", estimate, throw=True)
	values = option_values(estimate, proposal)
	company = frappe.db.get_value("Solar Design Estimate", estimate, "company")
	payload = dict(values, company=company, transaction_date=today(), items=[{"solar_package": values["solar_package"], "qty": 1}],
		taxes_and_charges=frappe.db.get_value("Sales Taxes and Charges Template", {"company": company, "is_default": 1, "disabled": 0}, "name"),
		terms=get_value("terms_and_conditions_text") or None)
	if name:
		payload.pop("transaction_date")
	result = cost_estimate.save(payload, name)
	return result


def apply_option(doc, method=None):
	"""Quotation before_validate: a quotation for a design option charges that option.

	One package line at the option's plant total, described as the proposal describes the
	plant; the option's Special Discount as the discount. Typed prices give way to the
	proposal's - the option was finalised there.
	"""
	if not doc.get("solar_design_estimate") or not frappe.db.exists("Solar Design Estimate", doc.solar_design_estimate):
		return
	est = frappe.get_doc("Solar Design Estimate", doc.solar_design_estimate)
	package = est.solar_package or doc.get("solar_package")
	if not package:
		return
	from a3_sola.api.cost_estimate import _package_item

	item_code = _package_item(package)
	rows = doc.get("items") or []
	# Only a quotation that is the option - no lines yet, or the package's own line - is
	# priced from it. One whose lines were set some other way is left as it was written.
	if any(not (r.get("solar_package") or r.item_code == item_code) for r in rows if r.item_code):
		return
	line = next((r for r in rows if r.get("solar_package") or r.item_code == item_code), None)
	if not line:
		doc.set("items", [])
		line = doc.append("items", {"item_code": item_code, "qty": 1, "uom": frappe.db.get_value("Item", item_code, "stock_uom")})
	else:
		doc.set("items", [line])
	line.item_code = item_code
	line.solar_package = package
	line.qty = 1
	line.rate = line.price_list_rate = plant_amount(est)
	line.discount_percentage = 0
	line.description = plant_description(est)
	if not line.get("item_name"):
		line.item_name = frappe.db.get_value("Item", item_code, "item_name")
	doc.solar_package = package
	discount = special_discount(est)
	if discount and not flt(doc.discount_amount) and not flt(doc.additional_discount_percentage):
		doc.apply_discount_on = "Net Total"
		doc.discount_amount = discount
	doc.run_method("calculate_taxes_and_totals")


def quotation_print_doc(quotation):
	"""Jinja: the Solar Quotation print's record for the pages after the cover - its option,
	with the proposal's customer and site details and the quotation's own number, date and
	price."""
	if not quotation.get("solar_design_estimate"):
		return None
	return option_doc(quotation.solar_design_estimate, quotation.get("solar_proposal"), quotation)


@frappe.whitelist()
def option_head(estimate, proposal=None):
	"""For the desk form: the quotation's head for an option, and the package line's item."""
	from a3_sola.api.cost_estimate import _package_item

	frappe.has_permission("Solar Design Estimate", "read", estimate, throw=True)
	values = option_values(estimate, proposal)
	values["item_code"] = _package_item(values["solar_package"]) if values.get("solar_package") else None
	values["estimates"] = [o["estimate"] for p in options(proposal=values["solar_proposal"])["proposals"] for o in p["options"]] \
		if values.get("solar_proposal") else []
	return values


@frappe.whitelist()
def proposal_estimates(proposal=None, lead=None):
	"""The design estimates the Design Estimate field offers: the proposal's options, else the lead's."""
	data = options(lead=lead, proposal=proposal)
	return [o["estimate"] for p in data["proposals"] for o in p["options"]] + [o["estimate"] for o in data["loose"]]


# ------------------------------------------------------------------ the portal page
def page_context(context, name=None):
	"""Context for /a3solaportal/quotations/new and /a3solaportal/quotations/<name>."""
	from a3_sola.api.portal_fields import link_title
	from a3_sola.www.a3solaportal import fill_shell
	from a3_sola.www.a3solaportal.quotations_seed import quotation_aside

	doc = None
	if name:
		if not frappe.db.exists("Quotation", name):
			raise frappe.DoesNotExistError(_("That quotation does not exist."))
		doc = frappe.get_doc("Quotation", name)
		doc.check_permission("read")
	else:
		frappe.has_permission("Quotation", "create", throw=True)
	crumbs = [{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Quotation", "href": "/a3solaportal/quotations"},
		{"label": name or "New"}]
	fill_shell(context, active_route="/a3solaportal/quotations", page_title=name or _("New quotation"), crumbs=crumbs)

	lead, proposal, estimate = "", "", ""
	if doc:
		estimate, proposal = doc.get("solar_design_estimate") or "", doc.get("solar_proposal") or ""
		lead = frappe.db.get_value("Solar Design Estimate", estimate, "lead") if estimate else ""
		if not lead and doc.quotation_to == "Lead":
			lead = doc.party_name
		quotation_aside(context, name)
	else:
		form = frappe.form_dict
		lead = (form.get("lead") or "").strip()
		if form.get("source_dt") == "Solar Proposal" and frappe.db.exists("Solar Proposal", form.get("source")):
			proposal = form.get("source")
			lead = frappe.db.get_value("Solar Proposal", proposal, "lead") or lead
		elif form.get("source_dt") == "Lead":
			lead = form.get("source") or lead
	editable = (not doc) or (doc.docstatus == 0 and doc.has_permission("write"))
	# The leads a quotation can be raised for: those with a proposal or a design estimate on file.
	leads = sorted((set(frappe.get_list("Solar Proposal", filters={"docstatus": ["<", 2]}, pluck="lead"))
		| set(frappe.get_list("Solar Design Estimate", filters={"docstatus": ["<", 2]}, pluck="lead"))) - {None, ""})
	context.quotation = doc
	context.quote_name = name or ""
	context.title = name or _("New quotation")
	context.editable = editable
	context.submitted = bool(doc and doc.docstatus == 1)
	context.lead_choices = [{"value": l, "label": link_title("Lead", l)} for l in leads]
	context.state_json = frappe.as_json({"lead": lead or "", "proposal": proposal, "estimate": estimate, "name": name or "",
		"editable": editable, "status": doc.status if doc else "", "docstatus": doc.docstatus if doc else 0})
	context.pdf_route = "/api/method/a3_sola.api.quotation_option.pdf?name=" + frappe.utils.quote(name) if name else ""
	if doc and doc.docstatus < 2:
		# View, download and send it to the customer: the square buttons by Back, held
		# (greyed, with the reason) until the quotation is submitted.
		from a3_sola.api.portal_share import share_links

		context.share = share_links(doc, context.pdf_route)
		# Download asks which print: each of the quotation's formats, its own buttons.
		context.share["formats"] = [{
			"name": f, "default": f == DEFAULT_PRINT_FORMAT,
			"view": context.pdf_route + "&print_format=" + frappe.utils.quote(f),
			"download": context.pdf_route + "&download=1&print_format=" + frappe.utils.quote(f),
		} for f in print_formats()]
	context.desk_route = "/app/quotation/" + frappe.utils.quote(name) if name else ""
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context


#: The quotation's own print, listed first and used where none is named.
DEFAULT_PRINT_FORMAT = "Solar Quotation"


def print_formats():
	"""The print formats a quotation can be downloaded in: ours first, then the other
	enabled ones for Quotation, then Frappe's built-in Standard."""
	names = frappe.get_all("Print Format", filters={"doc_type": "Quotation", "disabled": 0}, pluck="name", order_by="name")
	ordered = ([DEFAULT_PRINT_FORMAT] if DEFAULT_PRINT_FORMAT in names else []) + [n for n in names if n != DEFAULT_PRINT_FORMAT]
	return ordered + ["Standard"]


@frappe.whitelist()
def pdf(name, download=0, print_format=None):
	"""The quotation as the customer receives it - the Solar Quotation print, or another of
	its print formats (print_formats) - to read in the browser, or to save with `download=1`."""
	from frappe.utils.pdf import get_pdf

	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("read")
	if doc.docstatus != 1:
		# Its PDF is the quotation as issued: a draft has none yet.
		frappe.throw(_("Submit the quotation first to view, download or send its PDF."), title=_("Not Issued Yet"))
	print_format = print_format or DEFAULT_PRINT_FORMAT
	if print_format not in print_formats():
		frappe.throw(_("{0} is not a print format for quotations.").format(print_format))
	html = frappe.get_print("Quotation", name, print_format=print_format, no_letterhead=0)
	suffix = "" if print_format == DEFAULT_PRINT_FORMAT else " - " + print_format
	from a3_sola.api.documents import customer_file_name

	frappe.local.response.filename = customer_file_name(doc.customer_name or doc.party_name, "Quotation {0}{1}".format(name, suffix))
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "download" if cint(download) else "pdf"


def ensure_party(doc, method=None):
	"""Quotation before_validate: a quotation for a consumer is raised to its Customer.

	The consumer is converted to an ERPNext Customer here if nobody did it by hand, and a
	quotation still addressed to the consumer's lead is moved to that Customer. One already
	raised to some other Customer is left as written.
	"""
	consumer = doc.get("solar_consumer")
	if not consumer or not frappe.db.exists("Solar Consumer", consumer):
		return
	from a3_sola.solar_crm.doctype.solar_consumer.solar_consumer import ensure_customer

	if doc.quotation_to == "Customer" and doc.party_name:
		linked = frappe.db.get_value("Solar Consumer", consumer, "customer")
		if linked and linked != doc.party_name:
			return
		if not linked:
			frappe.db.set_value("Solar Consumer", consumer, "customer", doc.party_name)
			return
	customer = ensure_customer(consumer)
	doc.quotation_to = "Customer"
	doc.party_name = customer
	doc.customer_name = frappe.db.get_value("Customer", customer, "customer_name")
