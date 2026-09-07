# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cost estimates: ERPNext Quotations, built in the portal.

The portal's Customer Relations menu calls a Quotation a cost estimate, because that is
what the sales team hands a lead. The builder is one page: the company's Solar Packages
and their bill of materials on the left, a point-of-sale style cost panel on the right,
with the solar layer and the terms on their own tabs. Every figure in the panel comes from
this module, which lets ERPNext's own controllers price, discount and tax the document -
so the number the person sees is exactly the number the saved Quotation carries.

Nothing here bypasses the Quotation's own rules. `overrides.quotation` still forbids a
subsidy in the items or taxes and still gates submission on the design estimate and the
eligibility check; this module only assembles the document and reports back.
"""

import json

import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, sanitize_html, today

from a3_sola.api.settings import get_value
from a3_sola.overrides import quotation as quotation_rules

SLUG = "cost-estimates"
DEFAULT_VALIDITY_DAYS = 30
PARTY_TYPES = ("Lead", "Customer")
PARTY_LIMIT = 300
#: The value the Terms tab uses for the company's own standard terms from Settings.
SETTINGS_TERMS = "__settings"

#: What the builder may set on the Quotation head. Anything else posted is ignored.
HEADER_FIELDS = (
	"quotation_to", "party_name", "transaction_date", "valid_till", "order_type",
	"taxes_and_charges", "apply_discount_on", "additional_discount_percentage", "discount_amount",
	"tc_name", "terms",
)
#: The solar layer - the app's own custom fields on Quotation.
SOLAR_LINK_FIELDS = (
	"solar_consumer", "solar_design_estimate", "selected_option", "subsidy_eligibility_check",
	"solar_proposal", "solar_package",
)
FINANCE_FIELDS = (
	"is_financed", "lender", "lender_branch", "loan_scheme", "jan_samarth_id",
	"loan_sanction_no", "sanctioned_amount", "finance_status",
)
#: Read-only solar figures the panel displays. Filled from the estimate where there is one,
#: and from the package where there is not - never typed.
SOLAR_DISPLAY_FIELDS = (
	"subsidy_scheme", "capacity_kw", "gross_amount", "expected_subsidy_to_customer",
	"net_payable_by_customer", "estimated_annual_savings", "simple_payback_years", "net_meter_mode",
	"kseb_application_fee", "kseb_registration_fee", "kseb_registration_refundable",
	"net_meter_charge", "statutory_total",
)


# ------------------------------------------------------------------ helpers
def _company():
	return frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")


def _payload(payload):
	if isinstance(payload, str):
		payload = json.loads(payload or "{}")
	return frappe._dict(payload or {})


def route_of(name):
	return "/a3solaportal/{0}/{1}".format(SLUG, frappe.utils.quote(name))


def desk_route(name):
	return "/app/quotation/{0}".format(frappe.utils.quote(name))


# ---------------------------------------------------------------- catalogue
@frappe.whitelist()
def catalogue():
	"""Everything the left-hand side offers: packages with their BOM, add-on items,
	the tax templates and the terms templates. One call, on page load."""
	frappe.has_permission("Quotation", "read", throw=True)
	company = _company()
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")

	packages = frappe.get_all(
		"Solar Package",
		filters={"company": company, "is_active": 1},
		fields=[
			"name", "specification_code", "package_name", "capacity_kw", "system_type", "connection_type",
			"inverter_topology", "is_dcr_compliant", "area_required_sqft", "tier", "item",
			"module_specification", "module_make", "module_wattage", "module_count",
			"inverter_1_specification", "inverter_1_make", "inverter_1_capacity_kw", "inverter_1_count",
			"inverter_2_specification", "inverter_2_make", "inverter_2_capacity_kw", "inverter_2_count",
			"cost_option_1", "cost_option_2", "standard_discount", "indicative_subsidy", "net_rate",
			"statutory_total", "expected_daily_units_low", "expected_daily_units_high", "warranty_years",
		],
		order_by="capacity_kw asc, package_name asc",
	)
	makes = {
		m.name: m.make_name
		for m in frappe.get_all("Component Make", filters={"company": company}, fields=["name", "make_name"])
	}
	for pkg in packages:
		pkg.module_make_name = makes.get(pkg.module_make, pkg.module_make)
		pkg.options = []
		for n in (1, 2):
			spec = pkg.get(f"inverter_{n}_specification")
			cost = flt(pkg.get(f"cost_option_{n}"))
			if not spec and not cost:
				continue
			pkg.options.append({
				"option": n,
				"label": _("Option {0}").format(n),
				"inverter_make": makes.get(pkg.get(f"inverter_{n}_make"), pkg.get(f"inverter_{n}_make")) or "",
				"inverter_specification": spec or "",
				"inverter_capacity_kw": flt(pkg.get(f"inverter_{n}_capacity_kw")),
				"inverter_count": cint(pkg.get(f"inverter_{n}_count")),
				"rate": cost,
			})
		pkg.components = [
			{
				"component_type": c.component_type, "specification": c.specification or "",
				"make": makes.get(c.make, c.make) or "", "alternate_makes": c.alternate_makes or "",
				"qty": flt(c.qty), "uom": c.uom or "",
			}
			for c in frappe.get_all(
				"Solar Package Component", filters={"parent": pkg.name, "parenttype": "Solar Package"},
				fields=["component_type", "specification", "make", "alternate_makes", "qty", "uom"],
				order_by="display_order asc, idx asc",
			)
		]
		pkg.bom_items = []
		if pkg.item:
			bom = frappe.db.get_value("BOM", {"item": pkg.item, "is_active": 1, "docstatus": 1}, "name", order_by="is_default desc")
			if bom:
				pkg.bom_items = frappe.get_all(
					"BOM Item", filters={"parent": bom}, fields=["item_code", "item_name", "qty", "uom"], order_by="idx"
				)

	package_items = {p.item for p in packages if p.item}
	addons = []
	for item in frappe.get_all(
		"Item",
		filters={"is_sales_item": 1, "disabled": 0, "has_variants": 0},
		fields=["name", "item_name", "item_group", "stock_uom", "standard_rate", "description"],
		order_by="item_group asc, item_name asc",
		limit_page_length=200,
	):
		if item.name in package_items:
			continue
		rate = None
		if price_list:
			rate = frappe.db.get_value(
				"Item Price", {"item_code": item.name, "price_list": price_list, "selling": 1}, "price_list_rate"
			)
		addons.append({
			"item_code": item.name, "item_name": item.item_name or item.name, "item_group": item.item_group,
			"uom": item.stock_uom or "Nos", "rate": flt(rate if rate is not None else item.standard_rate),
			"description": frappe.utils.strip_html(item.description or "")[:140],
		})

	taxes = frappe.get_all(
		"Sales Taxes and Charges Template",
		filters={"company": company, "disabled": 0},
		fields=["name", "title", "is_default"],
		order_by="is_default desc, title asc",
	)
	for t in taxes:
		t.rows = frappe.get_all(
			"Sales Taxes and Charges", filters={"parent": t.name}, fields=["description", "rate"], order_by="idx"
		)

	terms_templates = [
		{"name": t.name, "title": t.title or t.name, "terms": sanitize_html(t.terms or "")}
		for t in frappe.get_all(
			"Terms and Conditions", filters={"disabled": 0}, fields=["name", "title", "terms", "selling"],
			order_by="title asc",
		)
		if cint(t.selling) or True
	]
	settings_terms = sanitize_html(get_value("terms_and_conditions_text") or "")
	if settings_terms:
		terms_templates.insert(0, {"name": SETTINGS_TERMS, "title": _("Company standard terms"), "terms": settings_terms})

	return {
		"company": company,
		"currency": frappe.db.get_value("Company", company, "default_currency") or "INR",
		"packages": packages,
		"addons": addons,
		"taxes": taxes,
		"default_tax_template": next((t.name for t in taxes if t.is_default), taxes[0].name if taxes else None),
		"terms_templates": terms_templates,
		"notes": {
			"delivery": sanitize_html(get_value("delivery_schedule_text") or ""),
			"gst": sanitize_html(get_value("gst_treatment_note") or ""),
			"subsidy": sanitize_html(get_value("subsidy_note_text") or ""),
		},
		"validity_days": DEFAULT_VALIDITY_DAYS,
		"today": today(),
	}


@frappe.whitelist()
def parties(quotation_to="Lead", q=None):
	"""Who the estimate is for: leads by default, customers on request."""
	if quotation_to not in PARTY_TYPES:
		frappe.throw(_("Quotation To must be Lead or Customer."))
	frappe.has_permission(quotation_to, "read", throw=True)
	like = "%{0}%".format((q or "").strip()) if q else None
	company = _company()
	if quotation_to == "Lead":
		fields = ["name", "lead_name", "company_name", "mobile_no", "phone", "email_id", "city", "status", "approx_capacity_kw"]
		filters = {"company": company} if frappe.get_meta("Lead").has_field("company") and company else {}
		or_filters = [[f, "like", like] for f in ("name", "lead_name", "company_name", "mobile_no", "email_id")] if like else None
		rows = frappe.get_list("Lead", filters=filters, or_filters=or_filters, fields=fields,
			order_by="modified desc", limit_page_length=PARTY_LIMIT)
		return [
			{
				"value": r.name,
				"label": r.lead_name or r.company_name or r.name,
				"sub": " · ".join(v for v in (r.company_name if r.company_name != r.lead_name else None, r.mobile_no or r.phone, r.city, r.status) if v),
				"capacity_kw": flt(r.approx_capacity_kw),
			}
			for r in rows
		]
	fields = ["name", "customer_name", "mobile_no", "email_id", "customer_group", "territory"]
	or_filters = [[f, "like", like] for f in ("name", "customer_name", "mobile_no", "email_id")] if like else None
	rows = frappe.get_list("Customer", or_filters=or_filters, fields=fields, order_by="modified desc", limit_page_length=PARTY_LIMIT)
	return [
		{"value": r.name, "label": r.customer_name or r.name,
		 "sub": " · ".join(v for v in (r.mobile_no, r.email_id, r.territory) if v), "capacity_kw": 0}
		for r in rows
	]


@frappe.whitelist()
def references(quotation_to="Lead", party_name=None):
	"""The solar records already on file for the party, so the estimate links to them
	rather than starting from nothing: the consumer, its design estimates and their
	options, proposals and eligibility checks - and which of each to default to."""
	if quotation_to not in PARTY_TYPES or not party_name:
		return {}
	if not frappe.db.exists(quotation_to, party_name):
		frappe.throw(_("{0} {1} does not exist.").format(quotation_to, party_name), frappe.DoesNotExistError)
	party = frappe.get_doc(quotation_to, party_name)
	party.check_permission("read")

	out = frappe._dict(party={}, consumers=[], estimates=[], proposals=[], eligibility_checks=[], defaults={})
	consumer_names = []
	if quotation_to == "Lead":
		out.party = {
			"name": party.name, "label": party.lead_name or party.company_name or party.name,
			"mobile_no": party.mobile_no or party.phone, "email_id": party.email_id, "city": party.city,
			"capacity_kw": flt(party.get("approx_capacity_kw")), "avg_monthly_bill": flt(party.get("avg_monthly_bill")),
			"subsidy_scheme": party.get("subsidy_scheme"), "consumer_category": party.get("consumer_category"),
			"connection_type": party.get("connection_type"), "discom": party.get("discom"),
		}
		if party.get("solar_consumer") and frappe.db.exists("Solar Consumer", party.solar_consumer):
			consumer_names.append(party.solar_consumer)
		consumer_names += [
			c for c in frappe.get_all("Solar Consumer", filters={"lead": party.name}, pluck="name") if c not in consumer_names
		]
	else:
		out.party = {
			"name": party.name, "label": party.customer_name or party.name,
			"mobile_no": party.mobile_no, "email_id": party.email_id, "city": None, "capacity_kw": 0,
		}
		consumer_names = frappe.get_all("Solar Consumer", filters={"customer": party.name}, pluck="name")

	if consumer_names:
		out.consumers = frappe.get_all(
			"Solar Consumer", filters={"name": ["in", consumer_names]},
			fields=["name", "consumer_name", "consumer_number", "consumer_category", "connection_type", "discom", "status"],
		)
		out.estimates = frappe.get_all(
			"Solar Design Estimate",
			filters={"solar_consumer": ["in", consumer_names], "docstatus": ["<", 2]},
			fields=["name", "solar_consumer", "final_capacity_kw", "total_project_cost", "applicable_subsidy_amount",
				"subsidy_scheme", "docstatus", "solar_package"],
			order_by="docstatus desc, creation desc",
		)
		for est in out.estimates:
			est.options = frappe.get_all(
				"Design Estimate Option", filters={"parent": est.name},
				fields=["option_name", "solar_package", "total_option_cost", "is_recommended"], order_by="idx",
			)
		out.proposals = frappe.get_all(
			"Solar Proposal", filters={"solar_consumer": ["in", consumer_names]},
			fields=["name", "status", "customer_name"], order_by="creation desc",
		)
		out.eligibility_checks = frappe.get_all(
			"Subsidy Eligibility Check", filters={"solar_consumer": ["in", consumer_names], "docstatus": ["<", 2]},
			fields=["name", "overall_result", "check_date"], order_by="creation desc",
		)
	if quotation_to == "Lead":
		# Proposals and checks raised on the lead before it had a consumer.
		seen = {p.name for p in out.proposals}
		out.proposals += [p for p in frappe.get_all("Solar Proposal", filters={"lead": party.name},
			fields=["name", "status", "customer_name"], order_by="creation desc") if p.name not in seen]
		seen = {c.name for c in out.eligibility_checks}
		out.eligibility_checks += [c for c in frappe.get_all("Subsidy Eligibility Check",
			filters={"lead": party.name, "docstatus": ["<", 2]}, fields=["name", "overall_result", "check_date"],
			order_by="creation desc") if c.name not in seen]

	out.defaults = {
		"solar_consumer": out.consumers[0].name if out.consumers else None,
		"solar_design_estimate": out.estimates[0].name if out.estimates else None,
		"subsidy_eligibility_check": out.eligibility_checks[0].name if out.eligibility_checks else None,
		"solar_proposal": out.proposals[0].name if out.proposals else None,
	}
	return out


# ------------------------------------------------------------ the document
def _apply(doc, payload):
	"""Lay the builder's payload onto a Quotation, then let ERPNext price it."""
	company = doc.company or payload.get("company") or _company()
	doc.company = company

	for field in HEADER_FIELDS:
		if field in payload:
			doc.set(field, payload.get(field) or None)
	if doc.quotation_to not in PARTY_TYPES:
		frappe.throw(_("Quotation To must be Lead or Customer."))
	if not doc.party_name:
		frappe.throw(_("Choose who this estimate is for."), frappe.MandatoryError)
	if not frappe.db.exists(doc.quotation_to, doc.party_name):
		frappe.throw(_("{0} {1} does not exist.").format(doc.quotation_to, doc.party_name), frappe.DoesNotExistError)
	doc.order_type = doc.order_type or "Sales"
	doc.transaction_date = doc.transaction_date or today()
	if not doc.valid_till:
		doc.valid_till = add_days(doc.transaction_date, DEFAULT_VALIDITY_DAYS)
	if getdate(doc.valid_till) < getdate(doc.transaction_date):
		frappe.throw(_("Valid Till cannot be before the quotation date."))

	for field in SOLAR_LINK_FIELDS + FINANCE_FIELDS:
		if field in payload:
			value = payload.get(field)
			if field in ("is_financed",):
				value = 1 if str(value).lower() in ("1", "true", "on", "yes") else 0
			elif field == "sanctioned_amount":
				value = flt(value)
			doc.set(field, value if value not in ("", None) else None)

	# Discounts: one or the other. A percentage recomputes the amount on every save.
	doc.apply_discount_on = doc.apply_discount_on or "Grand Total"
	doc.additional_discount_percentage = flt(payload.get("additional_discount_percentage"))
	doc.discount_amount = flt(payload.get("discount_amount")) if not doc.additional_discount_percentage else 0

	# Items: rebuilt from the panel every time. A package line without an Item yet gets
	# one created, the same way the desk button does.
	if "items" in payload:
		doc.set("items", [])
		for row in payload.get("items") or []:
			row = frappe._dict(row)
			item_code = row.get("item_code")
			if not item_code and row.get("solar_package"):
				item_code = _package_item(row.solar_package)
			if not item_code:
				frappe.throw(_("Line {0} has no item.").format(row.get("item_name") or "?"))
			if not frappe.db.exists("Item", item_code):
				frappe.throw(_("Item {0} does not exist.").format(item_code), frappe.DoesNotExistError)
			line = {
				"item_code": item_code,
				"qty": flt(row.get("qty")) or 1,
				"rate": flt(row.get("rate")),
				"description": row.get("description") or None,
				"uom": row.get("uom") or None,
			}
			if doc.meta.get_field("items") and frappe.get_meta("Quotation Item").has_field("solar_package"):
				line["solar_package"] = row.get("solar_package") or None
				line["package_option"] = row.get("package_option") or None
			doc.append("items", line)
	if not doc.get("items"):
		frappe.throw(_("Add at least one package or item to the estimate."), frappe.MandatoryError)

	# Taxes come from the chosen template, wholesale. Changing the template replaces them.
	if "taxes_and_charges" in payload or not doc.get("taxes"):
		doc.set("taxes", [])
		if doc.taxes_and_charges:
			for tax in get_taxes_and_charges("Sales Taxes and Charges Template", doc.taxes_and_charges) or []:
				doc.append("taxes", tax)

	doc.run_method("set_missing_values")
	doc.run_method("calculate_taxes_and_totals")
	_solar_figures(doc)
	return doc


def _package_item(package):
	from a3_sola.solar_crm.doctype.solar_package.solar_package import create_item_and_bom

	item = frappe.db.get_value("Solar Package", package, "item")
	if item:
		return item
	create_item_and_bom(package)
	return frappe.db.get_value("Solar Package", package, "item")


def _solar_figures(doc):
	"""The display-only solar layer. From the design estimate when the quotation is tied
	to one, which the Quotation rules enforce; otherwise indicative figures from the
	package, so an estimate raised straight off a lead still shows what the customer
	would net. The subsidy is never a line, a tax or a discount - only these fields."""
	if not doc.get("solar_package"):
		first = next((r.get("solar_package") for r in doc.items if r.get("solar_package")), None)
		if first:
			doc.solar_package = first

	if doc.get("solar_consumer") and doc.get("solar_design_estimate"):
		quotation_rules.pull_from_estimate(doc)
		return

	if doc.get("solar_package") and frappe.db.exists("Solar Package", doc.solar_package):
		pkg = frappe.get_cached_doc("Solar Package", doc.solar_package)
		category = None
		if doc.get("solar_consumer"):
			category = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "consumer_category")
		elif doc.quotation_to == "Lead":
			category = frappe.db.get_value("Lead", doc.party_name, "consumer_category")
		subsidised = (category or "Residential") == "Residential"
		doc.subsidy_scheme = get_value("default_subsidy_scheme") if subsidised else None
		doc.capacity_kw = flt(pkg.capacity_kw)
		doc.expected_subsidy_to_customer = flt(pkg.indicative_subsidy) if subsidised else 0
		doc.kseb_application_fee = flt(pkg.kseb_application_fee)
		doc.kseb_registration_fee = flt(pkg.kseb_registration_fee)
		doc.kseb_registration_refundable = flt(pkg.kseb_registration_refundable)
		doc.net_meter_charge = flt(pkg.net_meter_charge)
		doc.statutory_total = flt(pkg.statutory_total)
		doc.net_meter_mode = doc.net_meter_mode or "Purchased by Customer"
	else:
		doc.capacity_kw = 0
		doc.expected_subsidy_to_customer = 0
	doc.gross_amount = flt(doc.rounded_total or doc.grand_total)
	doc.net_payable_by_customer = flt(doc.gross_amount) - flt(doc.expected_subsidy_to_customer)


def summary(doc):
	"""What the panel shows. Every number is ERPNext's own."""
	return {
		"name": doc.name if not doc.get("__islocal") else None,
		"docstatus": doc.docstatus,
		"status": doc.get("status"),
		"editable": doc.docstatus == 0,
		"route": route_of(doc.name) if doc.name and not doc.get("__islocal") else None,
		"desk": desk_route(doc.name) if doc.name and not doc.get("__islocal") else None,
		"header": {f: doc.get(f) for f in HEADER_FIELDS + ("company", "currency", "customer_name", "title")},
		"solar": {f: doc.get(f) for f in SOLAR_LINK_FIELDS + FINANCE_FIELDS + SOLAR_DISPLAY_FIELDS},
		"items": [
			{
				"idx": r.idx, "item_code": r.item_code, "item_name": r.item_name, "description": frappe.utils.strip_html(r.description or ""),
				"qty": flt(r.qty), "uom": r.uom, "rate": flt(r.rate), "amount": flt(r.amount),
				"solar_package": r.get("solar_package"), "package_option": r.get("package_option"),
			}
			for r in doc.items
		],
		"taxes": [{"description": t.description, "rate": flt(t.rate), "tax_amount": flt(t.tax_amount)} for t in doc.taxes],
		"totals": {
			"total": flt(doc.total), "net_total": flt(doc.net_total),
			"discount_amount": flt(doc.discount_amount), "additional_discount_percentage": flt(doc.additional_discount_percentage),
			"total_taxes_and_charges": flt(doc.total_taxes_and_charges),
			"grand_total": flt(doc.grand_total), "rounded_total": flt(doc.rounded_total),
			"rounding_adjustment": flt(doc.rounding_adjustment), "in_words": doc.get("in_words") or "",
		},
	}


@frappe.whitelist()
def preview(payload=None):
	"""Price the panel without saving anything. Same code path as save, minus the write."""
	frappe.has_permission("Quotation", "read", throw=True)
	doc = frappe.new_doc("Quotation")
	_apply(doc, _payload(payload))
	doc.flags.ignore_permissions = True
	return summary(doc)


@frappe.whitelist()
def load(name):
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("read")
	out = summary(doc)
	out["editable"] = doc.docstatus == 0 and doc.has_permission("write")
	return out


@frappe.whitelist()
def save(payload=None, name=None):
	"""Create or update a draft. Submitted estimates are amended from ERPNext."""
	payload = _payload(payload)
	if name:
		doc = frappe.get_doc("Quotation", name)
		doc.check_permission("write")
		if doc.docstatus != 0:
			frappe.throw(_("{0} is {1}. Amend it from ERPNext to change it.").format(name, doc.status))
	else:
		frappe.has_permission("Quotation", "create", throw=True)
		doc = frappe.new_doc("Quotation")
	_apply(doc, payload)
	doc.save()
	return summary(doc)


@frappe.whitelist()
def submit(name):
	"""Submit a saved draft. The Quotation's own gates decide; their messages come back."""
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("submit")
	doc.submit()
	return summary(doc)
