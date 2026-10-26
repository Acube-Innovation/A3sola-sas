# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A design estimate has its own Optional Add-ons: each estimate on a package, with none yet,
takes the package's - what its proposal already printed from the package.
"""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_design_estimate")
	have = set(frappe.get_all("Solar Package Add-on", filters={"parenttype": "Solar Design Estimate"}, pluck="parent"))
	for est in frappe.get_all("Solar Design Estimate", filters={"solar_package": ["is", "set"]}, fields=["name", "solar_package"]):
		if est.name in have:
			continue
		rows = frappe.get_all("Solar Package Add-on", filters={"parent": est.solar_package, "parenttype": "Solar Package"},
			fields=["add_on_type", "item", "amount"], order_by="idx asc")
		for idx, row in enumerate(rows, start=1):
			frappe.get_doc({"doctype": "Solar Package Add-on", "parent": est.name, "parenttype": "Solar Design Estimate",
				"parentfield": "optional_add_ons", "idx": idx, **row}).db_insert()
