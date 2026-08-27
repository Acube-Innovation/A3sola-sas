# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Quotation: the solar layer, the subsidy rule and the submission gates."""

import frappe
from frappe import _
from frappe.utils import flt

FORBIDDEN_WORD = "subsidy"


def validate(doc, method=None):
	if not doc.get("solar_consumer"):
		reject_subsidy_rows(doc)
		return
	pull_from_estimate(doc)
	reject_subsidy_rows(doc)
	enforce_gates(doc, submitting=False)


def pull_from_estimate(doc):
	"""Every solar figure on a quotation is fetched, not typed."""
	if not doc.get("solar_design_estimate"):
		return
	estimate = frappe.get_cached_doc("Solar Design Estimate", doc.solar_design_estimate)

	doc.subsidy_scheme = estimate.subsidy_scheme
	doc.capacity_kw = flt(estimate.final_capacity_kw)
	doc.expected_subsidy_to_customer = flt(estimate.applicable_subsidy_amount)
	doc.estimated_annual_savings = flt(estimate.estimated_annual_savings)
	doc.simple_payback_years = flt(estimate.simple_payback_years)

	# Statutory charges are a reimbursement, not revenue. They print in their own block
	# and must never enter the items or taxes tables.
	doc.net_meter_mode = estimate.net_meter_mode
	doc.kseb_application_fee = flt(estimate.kseb_application_fee)
	doc.kseb_registration_fee = flt(estimate.kseb_registration_fee)
	doc.kseb_registration_refundable = flt(estimate.kseb_registration_refundable)
	doc.net_meter_charge = flt(estimate.net_meter_charge)
	doc.statutory_total = flt(estimate.statutory_total)

	option = None
	if doc.get("selected_option"):
		option = next((r for r in estimate.options if r.option_name == doc.selected_option), None)
		if not option:
			frappe.throw(
				_("Option {0} is not on design estimate {1}.").format(doc.selected_option, estimate.name)
			)
	elif len(estimate.options) == 1:
		option = estimate.options[0]
		doc.selected_option = option.option_name
	elif len(estimate.options) > 1:
		frappe.throw(
			_("Design estimate {0} quotes {1} options. Choose one in Selected Option.").format(
				estimate.name, len(estimate.options)
			),
			title=_("Select an Option"),
		)

	if option:
		doc.solar_package = option.solar_package
		doc.gross_amount = flt(option.total_option_cost)
	else:
		doc.gross_amount = flt(estimate.total_project_cost)

	doc.net_payable_by_customer = flt(doc.gross_amount) - flt(doc.expected_subsidy_to_customer)


def reject_subsidy_rows(doc):
	"""THE ABSOLUTE RULE.

	The subsidy is a government transfer to the customer that happens after commissioning.
	It is not our revenue, not our liability, and not a discount. It must never appear in
	the items table, the taxes table, or as a discount - only as a display field.
	"""
	for row in doc.get("items") or []:
		haystack = " ".join(str(v or "") for v in (row.item_name, row.description, row.item_code)).lower()
		if FORBIDDEN_WORD in haystack:
			frappe.throw(
				_("Item row {0} mentions a subsidy. The subsidy is a government transfer to the customer after commissioning - it can never be an item, a tax or a discount on a quotation.").format(
					row.idx
				),
				title=_("Subsidy on a Quotation"),
			)
	for row in doc.get("taxes") or []:
		if FORBIDDEN_WORD in str(row.description or "").lower():
			frappe.throw(
				_("Tax row {0} mentions a subsidy. The subsidy can never appear in the taxes table.").format(row.idx),
				title=_("Subsidy on a Quotation"),
			)


def enforce_gates(doc, submitting=True):
	"""Each gate raises a specific, actionable error naming the document to fix."""
	has_solar_item = bool(doc.get("solar_package")) or bool(doc.get("capacity_kw"))
	if not has_solar_item:
		return

	if not doc.get("solar_design_estimate"):
		if submitting:
			frappe.throw(
				_("This quotation carries a solar package but has no Design Estimate. Create and submit a Solar Design Estimate for {0} first.").format(
					doc.get("solar_consumer")
				),
				title=_("Design Estimate Required"),
			)
		return

	estimate = frappe.get_cached_doc("Solar Design Estimate", doc.solar_design_estimate)
	if submitting and estimate.docstatus != 1:
		frappe.throw(
			_("Design Estimate {0} is not submitted. Submit it before submitting this quotation.").format(
				frappe.utils.get_link_to_form("Solar Design Estimate", estimate.name)
			),
			title=_("Design Estimate Not Submitted"),
		)

	if flt(doc.capacity_kw) and flt(estimate.final_capacity_kw) and flt(doc.capacity_kw, 3) != flt(
		estimate.final_capacity_kw, 3
	):
		frappe.throw(
			_("Quotation capacity {0} kW does not match design estimate {1} at {2} kW. Correct one of them.").format(
				doc.capacity_kw, estimate.name, estimate.final_capacity_kw
			),
			title=_("Capacity Mismatch"),
		)

	check = doc.get("subsidy_eligibility_check")
	if check:
		result = frappe.db.get_value("Subsidy Eligibility Check", check, "overall_result")
		if result == "Not Eligible" and submitting:
			frappe.throw(
				_("Eligibility check {0} returned Not Eligible. Resolve the failing rules or record a waiver before submitting.").format(
					frappe.utils.get_link_to_form("Subsidy Eligibility Check", check)
				),
				title=_("Not Eligible"),
			)
	elif submitting and estimate.subsidy_scheme:
		frappe.throw(
			_("This quotation claims subsidy scheme {0} but has no Subsidy Eligibility Check. Run one for {1} first.").format(
				estimate.subsidy_scheme, doc.get("solar_consumer")
			),
			title=_("Eligibility Check Required"),
		)


def on_submit(doc, method=None):
	if not doc.get("solar_consumer"):
		return
	enforce_gates(doc, submitting=True)
	frappe.get_doc("Solar Consumer", doc.solar_consumer).set_status("Quoted")
	if doc.get("solar_proposal"):
		frappe.db.set_value("Solar Proposal", doc.solar_proposal, "status", "Accepted", update_modified=False)
