# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every package gets the Optional Add-ons tab filled with the usual two - one more of its
own panel, and the inverter warranty taken to 25 years - to edit per package."""

import frappe

from a3_sola.solar_crm.doctype.solar_package.solar_package import default_add_ons


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package_add_on")
	frappe.reload_doc("solar_crm", "doctype", "solar_package")
	have = set(frappe.get_all("Solar Package Add-on", filters={"parenttype": "Solar Package"}, pluck="parent"))
	for name in frappe.get_all("Solar Package", pluck="name"):
		if name in have:
			continue
		doc = frappe.get_doc("Solar Package", name)
		for row in default_add_ons(doc):
			doc.append("optional_add_ons", row)
		# Only the new rows are written: the package's own validation is not re-run on data
		# it may not pass today (an old price row, a lapsed make).
		for row in doc.optional_add_ons:
			row.db_insert()
