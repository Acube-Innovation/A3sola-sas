# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A design estimate has its own Optional Add-ons: each estimate on a package, with none yet,
takes the package's as Options - what its proposal already printed from the package.
"""

import frappe

from a3_sola.solar_crm.doctype.solar_package.solar_package import default_module


def execute():
	frappe.reload_doc("solar_crm", "doctype", "design_estimate_add_on")
	frappe.reload_doc("solar_crm", "doctype", "solar_design_estimate")
	have = set(frappe.get_all("Design Estimate Add-on", filters={"parenttype": "Solar Design Estimate"}, pluck="parent"))
	for est in frappe.get_all("Solar Design Estimate", filters={"solar_package": ["is", "set"]}, fields=["name", "solar_package"]):
		if est.name in have or not frappe.db.exists("Solar Package", est.solar_package):
			continue
		package = frappe.get_doc("Solar Package", est.solar_package)
		module = default_module(package)
		for idx, r in enumerate(package.get("optional_add_ons") or [], start=1):
			row = {"add_on_type": r.add_on_type or "Other", "item": r.item, "rate": r.amount, "amount": r.amount, "nos": 1, "is_option": 1}
			if r.add_on_type == "Extra Panel" and module:
				row.update({"panel_capacity_wp": module.module_wattage, "panel_make": module.module_make, "panel_count": 1})
			frappe.get_doc({"doctype": "Design Estimate Add-on", "parent": est.name, "parenttype": "Solar Design Estimate",
				"parentfield": "optional_add_ons", "idx": idx, **row}).db_insert()
