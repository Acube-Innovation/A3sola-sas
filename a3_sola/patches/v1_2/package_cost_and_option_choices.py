# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Packages carry their cost; each option row its panel, inverter and battery.

A package without a cost takes its default inverter's cost (else its default price row's).
Each sizing option row is given its package's cost and the panel, inverter and battery it
is built with: on the recommended row, the ones the estimate prices where its package
offers them; otherwise the package's defaults. Written straight to the rows, so submitted
estimates are filled in too and nothing is re-priced.
"""

import frappe
from frappe.utils import flt

from a3_sola.solar_crm.doctype.solar_package.solar_package import default_package_cost, package_components

CHOICES = (("panels", "panel_make"), ("inverters", "inverter_make"), ("batteries", "battery_make"))


def execute():
	for name in frappe.get_all("Solar Package", pluck="name"):
		doc = frappe.get_doc("Solar Package", name)
		if not flt(doc.package_cost):
			doc.db_set("package_cost", default_package_cost(doc), update_modified=False)
	frappe.clear_document_cache("Solar Package")

	rows = frappe.get_all("Design Estimate Sizing Option", filters={"parenttype": "Solar Design Estimate",
		"solar_package": ["is", "set"]}, fields=["name", "parent", "solar_package", "connection_type", "system_type", "is_recommended"])
	for row in rows:
		if not frappe.db.exists("Solar Package", row.solar_package):
			continue
		offered = package_components(row.solar_package, row.connection_type)
		values = {"package_cost": offered["package_cost"]}
		for table, field in CHOICES:
			choices = offered[table] if table != "batteries" or row.system_type in ("Off-Grid", "Hybrid") else []
			makes = [o["value"] for o in choices]
			priced = None
			if row.is_recommended and makes:
				priced = frappe.db.get_value(
					{"panels": "Design Estimate Panel", "inverters": "Design Estimate Inverter", "batteries": "Design Estimate Battery"}[table],
					{"parent": row.parent, "parenttype": "Solar Design Estimate", "is_option": 0, field: ["in", makes]}, field)
			values[field] = priced or next((o["value"] for o in choices if o["default"]), makes[0] if makes else None)
		frappe.db.set_value("Design Estimate Sizing Option", row.name, values, update_modified=False)
