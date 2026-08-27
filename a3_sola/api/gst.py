# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""GST valuation for solar EPC.

Solar EPC in India is a composite supply. The prevailing approach applies a 70:30 valuation
- 70% goods, 30% services - each at its own rate. Published sources still disagree, some
EPCs bill on separate lines for input-credit clarity, and the correct treatment depends on
contract structure. The client's own proposals quote a single all-inclusive figure and
state no basis at all.

So there is NO RATE CONSTANT ANYWHERE IN THIS MODULE. Everything is a Solar GST Valuation
Rule, and postings are gated on a recorded CA confirmation.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def resolve_valuation(company, consumer_category=None, on_date=None):
	"""The applicable rule, or a clear error - never a silent default."""
	on_date = getdate(on_date or today())
	rules = frappe.get_all(
		"Solar GST Valuation Rule",
		filters={"company": company, "is_active": 1, "effective_from": ["<=", on_date]},
		fields=["name", "applicable_consumer_category", "effective_to", "effective_from"],
		order_by="effective_from desc",
	)
	candidates = [
		r
		for r in rules
		if not r.effective_to or getdate(r.effective_to) >= on_date
	]
	if consumer_category:
		exact = [r for r in candidates if r.applicable_consumer_category == consumer_category]
		if exact:
			return exact[0].name
	generic = [r for r in candidates if r.applicable_consumer_category in ("All", None, "")]
	if generic:
		return generic[0].name

	frappe.throw(
		_("No active GST valuation rule for {0} on {1}. An invoice cannot be built without one.").format(
			company, on_date
		),
		title=_("GST Rule Missing"),
	)


def build_invoice_items(project, milestone_amount, rule_name):
	"""The item rows a Sales Invoice should carry under a valuation rule.

	Returns one blended row, two split rows, or a single row - whichever the rule says.
	"""
	rule = frappe.get_cached_doc("Solar GST Valuation Rule", rule_name)
	doc = frappe.get_doc("Project", project) if isinstance(project, str) else project
	amount = flt(milestone_amount)
	description = _("Grid connected rooftop solar power plant, {0} kWp").format(flt(doc.capacity_kw))

	if rule.valuation_mode == "Separate Line Items":
		goods = flt(amount * flt(rule.goods_value_percent) / 100.0, 2)
		services = flt(amount - goods, 2)
		return [
			{
				"item_code": rule.goods_item,
				"item_name": _("Solar plant - supply of goods"),
				"description": f"{description} - supply of goods",
				"qty": 1,
				"rate": goods,
				"item_tax_template": rule.goods_item_tax_template,
				"gst_hsn_code": rule.goods_hsn_code,
			},
			{
				"item_code": rule.services_item,
				"item_name": _("Solar plant - supply of services"),
				"description": f"{description} - erection, installation and commissioning",
				"qty": 1,
				"rate": services,
				"item_tax_template": rule.services_item_tax_template,
				"gst_hsn_code": rule.services_sac_code,
			},
		]

	# Blended and single-rate both produce one row; only the tax template differs.
	template = rule.goods_item_tax_template
	return [
		{
			"item_code": rule.goods_item,
			"item_name": _("Grid connected rooftop solar power plant"),
			"description": description,
			"qty": 1,
			"rate": flt(amount, 2),
			"item_tax_template": template,
			"gst_hsn_code": rule.goods_hsn_code,
		}
	]


def build_reimbursement_item(amount, reference):
	"""Statutory fees, billed OUTSIDE the composite supply.

	The client's proposals say so explicitly: DISCOM payments are reimbursed against
	receipts. This is never part of contract value and never taxed as if it were.
	"""
	return {
		"item_name": _("Statutory fees reimbursement"),
		"description": _("Reimbursement of DISCOM fees paid on your behalf. Receipt: {0}").format(
			reference or _("attached")
		),
		"qty": 1,
		"rate": flt(amount, 2),
	}


def postings_enabled(company=None):
	"""Both gates must be open. The CA gate cannot be bypassed."""
	enabled = frappe.db.get_single_value("A3 Sola Settings", "enable_accounting_postings")
	confirmed = frappe.db.get_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca")
	return bool(enabled and confirmed)
