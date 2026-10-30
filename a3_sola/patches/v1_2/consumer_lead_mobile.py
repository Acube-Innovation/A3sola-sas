# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer keeps two numbers: its own (Customer Mobile) and the one its enquiry came from
(Lead Mobile), which may be a relative's. Existing customers take the lead's number from
their lead."""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_consumer")
	frappe.db.sql("""update `tabSolar Consumer` c join `tabLead` l on l.name = c.lead
		set c.lead_mobile_no = coalesce(nullif(l.mobile_no, ''), nullif(l.phone, ''))
		where ifnull(c.lead_mobile_no, '') = ''""")
