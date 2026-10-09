# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Proposals carry their customer's site and connection, and a table of design estimates.

Section 1 is filled from the lead, its consumer and site survey, and the Design Estimates
table with the lead's estimates - the estimate the proposal was made from first, as the
base. Written directly, so submitted proposals are filled too and nothing is re-validated.
A proposal that cannot be filled is logged and left as it was.
"""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_proposal_estimate")
	frappe.reload_doc("solar_crm", "doctype", "solar_proposal")
	for name in frappe.get_all("Solar Proposal", pluck="name"):
		doc = frappe.get_doc("Solar Proposal", name)
		try:
			doc.fill_from_lead()
			if not doc.get("design_estimates"):
				doc.fill_design_estimates()
				for row in doc.design_estimates:
					row.db_insert()
			doc.db_update()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"proposal_details_and_estimates: {name} skipped")
		else:
			frappe.db.commit()
