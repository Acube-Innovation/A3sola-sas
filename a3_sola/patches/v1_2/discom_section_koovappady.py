# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Koovappady (5590, Ernakulam) as a customer's bill names it, so the portal's bill reader
(api/kseb_bill.py) finds it: its code put on the KSEB DISCOM's Koovappady, which had none, or
the section added where that DISCOM lacks it."""

import frappe

NAME, CODE, DISTRICT = "Koovappady", "5590", "Ernakulam"


def execute():
	from a3_sola.api.kseb_bill import kseb_discom

	discom = kseb_discom()
	if not discom:
		return
	section = frappe.db.get_value("DISCOM Section", {"section_name": NAME, "discom": discom}, ["name", "section_code"], as_dict=True)
	if section:
		if not section.section_code:
			frappe.db.set_value("DISCOM Section", section.name, "section_code", CODE)
	else:
		company = frappe.db.get_value("DISCOM", discom, "company") or frappe.db.get_value(
			"DISCOM Section", {"discom": discom}, "company")
		frappe.get_doc({"doctype": "DISCOM Section", "section_name": NAME, "section_code": CODE, "discom": discom,
			"district": DISTRICT, "company": company}).insert(ignore_permissions=True)
	frappe.db.commit()
