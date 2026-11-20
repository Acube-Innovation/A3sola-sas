# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Proposals stop quoting options taken off their design estimate.

Saving a proposal from the design page kept every estimate it already quoted, so an option
removed on the design page (its x) stayed in the proposal's page, PDF and comparison. A
draft is saved, which drops it (Solar Proposal.fill_design_estimates); an issued proposal
loses the row as it is, its other rows renumbered.
"""

import frappe

from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import dropped_options


def execute():
	rows = frappe.get_all("Solar Proposal Estimate", filters={"parenttype": "Solar Proposal"},
		fields=["name", "parent", "solar_design_estimate"])
	dropped = dropped_options(list({r.solar_design_estimate for r in rows}))
	for parent in sorted({r.parent for r in rows if r.solar_design_estimate in dropped}):
		docstatus = frappe.db.get_value("Solar Proposal", parent, "docstatus")
		if docstatus == 0:
			doc = frappe.get_doc("Solar Proposal", parent)
			doc.flags.ignore_permissions = True
			doc.save()
		elif docstatus == 1:
			for r in rows:
				if r.parent == parent and r.solar_design_estimate in dropped:
					frappe.db.delete("Solar Proposal Estimate", r.name)
			for idx, name in enumerate(frappe.get_all("Solar Proposal Estimate", filters={"parent": parent,
					"parenttype": "Solar Proposal"}, order_by="idx asc", pluck="name"), start=1):
				frappe.db.set_value("Solar Proposal Estimate", name, "idx", idx, update_modified=False)
