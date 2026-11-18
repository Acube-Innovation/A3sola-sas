# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Customers made before they had a Salutation take their lead's, where the lead has one,
and the records that show it follow: the ERPNext Customer, the draft surveys, eligibility
checks and proposals, and the projects. A proposal that already says something else keeps it.

The Quotation and Sales Order fields are made after the patches run (setup.install), so
those fill in the next time each is saved.
"""

import frappe


def execute():
	rows = frappe.db.sql(
		"""select c.name, l.salutation from `tabSolar Consumer` c join `tabLead` l on l.name = c.lead
		where ifnull(c.salutation, '') = '' and ifnull(l.salutation, '') != ''""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value("Solar Consumer", row.name, "salutation", row.salutation, update_modified=False)

	for consumer, salutation, customer in frappe.db.sql(
		"""select name, salutation, customer from `tabSolar Consumer` where ifnull(salutation, '') != ''"""
	):
		if customer:
			frappe.db.sql("""update `tabCustomer` set salutation = %s
				where name = %s and ifnull(salutation, '') = ''""", (salutation, customer))
		for doctype in ("Site Survey", "Subsidy Eligibility Check", "Solar Proposal"):
			frappe.db.sql(f"""update `tab{doctype}` set salutation = %s
				where solar_consumer = %s and docstatus = 0 and ifnull(salutation, '') = ''""", (salutation, consumer))
		frappe.db.sql("""update `tabSolar Installation` set salutation = %s
			where solar_consumer = %s and docstatus < 2 and ifnull(salutation, '') = ''""", (salutation, consumer))
