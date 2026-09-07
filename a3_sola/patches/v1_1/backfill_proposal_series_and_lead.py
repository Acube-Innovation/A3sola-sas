# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Repair proposals that were named by hand, and give every one of them its lead.

Until now every doctype in this app declared `autoname: Prompt` while also allocating its
own series in its controller. Frappe honours whichever arrives first, so a desk user who
typed a name got that name and the controller never ran: no sequence, no fiscal year, and
a file name that began with a bare dash. Server-side callers passed no name, so the series
worked for them and the hole stayed invisible.

The doctypes no longer prompt. This repairs the rows made while they did:

* a proposal with no sequence gets the next one for its company and financial year, and
  its file name recomposed on the client's convention;
* a proposal with no lead takes it from the estimate it quotes, or from its consumer,
  because a proposal now belongs to an enquiry and the version history hangs off that.

The documents keep the names they were given. Renaming them would break the Quotation,
Lead and Solar Installation links that already point at them, and those names are in the
client's WhatsApp history besides.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Solar Proposal"):
		return None

	repaired = {"sequence": 0, "lead": 0}

	for name, company, fiscal_year in frappe.db.sql(
		"""select name, company, fiscal_year from `tabSolar Proposal`
		   where ifnull(proposal_sequence, 0) = 0 order by creation"""
	):
		doc = frappe.get_doc("Solar Proposal", name)
		doc.set_fiscal_year()
		last = frappe.db.sql(
			"""select max(proposal_sequence) from `tabSolar Proposal`
			   where company = %s and fiscal_year = %s""",
			(doc.company, doc.fiscal_year),
		)[0][0]
		doc.proposal_sequence = (last or 0) + 1
		doc.compose_file_name()
		frappe.db.set_value(
			"Solar Proposal",
			name,
			{
				"proposal_sequence": doc.proposal_sequence,
				"fiscal_year": doc.fiscal_year,
				"proposal_file_name": doc.proposal_file_name,
			},
			update_modified=False,
		)
		repaired["sequence"] += 1

	for name, estimate, consumer in frappe.db.sql(
		"""select name, solar_design_estimate, solar_consumer from `tabSolar Proposal`
		   where ifnull(lead, '') = ''"""
	):
		lead = None
		if estimate:
			lead = frappe.db.get_value("Solar Design Estimate", estimate, "lead")
		if not lead and consumer:
			lead = frappe.db.get_value("Solar Consumer", consumer, "lead")
		if not lead:
			# An older proposal raised straight off a consumer that never came from an
			# enquiry. Nothing to point at, and inventing one would be worse than leaving it.
			continue
		frappe.db.set_value("Solar Proposal", name, "lead", lead, update_modified=False)
		repaired["lead"] += 1

	if repaired["sequence"] or repaired["lead"]:
		frappe.db.commit()
		frappe.clear_cache()
	return repaired
