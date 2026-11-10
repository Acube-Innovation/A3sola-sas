# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer holds what its lead says was asked for - Proposed System Size (kW) and Loan
Required - where the customer has nothing yet. What the lead does not say stays blank, to be
filled in on the customer's form, where both are asked for."""

import frappe

FIELDS = ("approx_capacity_kw", "loan_required")


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_consumer")
	rows = frappe.db.sql(
		"""select c.name, c.approx_capacity_kw, c.loan_required,
			l.approx_capacity_kw as lead_kw, l.loan_required as lead_loan
		from `tabSolar Consumer` c join `tabLead` l on l.name = c.lead""",
		as_dict=True,
	)
	for row in rows:
		values = {}
		if not row.approx_capacity_kw and row.lead_kw:
			values["approx_capacity_kw"] = row.lead_kw
		if not row.loan_required and row.lead_loan:
			values["loan_required"] = row.lead_loan
		if values:
			frappe.db.set_value("Solar Consumer", row.name, values, update_modified=False)
