# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEB sections customers' bills name that the DISCOM Section list lacked, so a bill read on
the portal (api/kseb_bill.py) finds them: Meloor (5650, Thrissur) and Thuravoor (5577,
Alappuzha). Added to the KSEB DISCOM, where no section of that name is."""

import frappe

#: (section name, KSEB section code, district) as the bill and the list write them.
SECTIONS = (("Meloor", "5650", "Thrissur"), ("Thuravoor", "5577", "Alappuzha"))


def execute():
	from a3_sola.api.kseb_bill import kseb_discom

	discom = kseb_discom()
	if not discom:
		return
	company = frappe.db.get_value("DISCOM", discom, "company") or frappe.db.get_value(
		"DISCOM Section", {"discom": discom}, "company")
	for name, code, district in SECTIONS:
		if frappe.db.exists("DISCOM Section", {"section_name": name, "discom": discom}):
			continue
		frappe.get_doc({"doctype": "DISCOM Section", "section_name": name, "section_code": code, "discom": discom,
			"district": district, "company": company}).insert(ignore_permissions=True)
	frappe.db.commit()
