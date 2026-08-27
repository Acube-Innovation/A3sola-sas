# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def validate(doc, method=None):
	"""Fetch capacity, subsidy and net cost from the linked design estimate."""
	if not doc.get("solar_design_estimate"):
		return
	estimate = frappe.get_cached_doc("Solar Design Estimate", doc.solar_design_estimate)
	doc.capacity_kw = flt(estimate.final_capacity_kw)
	doc.expected_subsidy_amount = flt(estimate.applicable_subsidy_amount)
	doc.net_customer_outflow = flt(estimate.net_cost_to_customer)
	if not doc.get("subsidy_scheme"):
		doc.subsidy_scheme = estimate.subsidy_scheme
