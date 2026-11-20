# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The KSEB fees are paid over and above an estimate's total, so the total a proposal keeps
for each of its estimates is worked out again without them."""

import frappe
from frappe.utils import flt


def execute():
	totals = {}
	for row in frappe.get_all("Solar Proposal Estimate", filters={"parenttype": "Solar Proposal"},
			fields=["name", "solar_design_estimate"]):
		estimate = row.solar_design_estimate
		if not estimate or not frappe.db.exists("Solar Design Estimate", estimate):
			continue
		if estimate not in totals:
			totals[estimate] = flt(frappe.get_doc("Solar Design Estimate", estimate).commercials()["total"])
		frappe.db.set_value("Solar Proposal Estimate", row.name, "total_amount", totals[estimate], update_modified=False)
