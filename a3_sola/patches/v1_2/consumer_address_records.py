# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer's address dropdowns offer only its own addresses, in full: each customer whose
installation site is typed but has no Address record gets one made from it, selected as its
installation address - and, where the permanent address is the same, as that too.
"""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_consumer")
	for name in frappe.get_all("Solar Consumer", pluck="name"):
		doc = frappe.get_doc("Solar Consumer", name)
		try:
			doc.ensure_address_record()
			if doc.installation_address and doc.permanent_address_same != "No" and not doc.get("permanent_address_record"):
				doc.db_set("permanent_address_record", frappe.db.get_value("Solar Consumer", name, "installation_address"),
					update_modified=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: address record for {name}")
