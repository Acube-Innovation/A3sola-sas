# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's Materials, Structure and Expenses rows depend on Items of the package's own, one
list for every table: a Material BOM row's inverters become its Depends On; a Structure row's
roof types and capacities are no longer read. Each row with an Item and no description takes
the Item's. A design estimate's copied tables are kept as they are: its basis is rewritten in
the new form, so its next save does not copy them again."""

import frappe

from a3_sola.api.package_bom_tables import item_text

TABLES = ("Solar Package Material BOM", "Solar Package Structure BOM", "Solar Package Expense")


def execute():
	if frappe.db.has_column("Solar Package Material BOM", "inverters"):
		frappe.db.sql("""update `tabSolar Package Material BOM` set depends_on = inverters
			where ifnull(depends_on, '') = '' and ifnull(inverters, '') != ''""")
	texts = {}
	for doctype in TABLES:
		for row in frappe.get_all(doctype, filters={"item": ["is", "set"], "description": ["is", "not set"]}, fields=["name", "item"]):
			if row.item not in texts:
				texts[row.item] = item_text(row.item) if frappe.db.exists("Item", row.item) else ""
			if texts[row.item]:
				frappe.db.set_value(doctype, row.name, "description", texts[row.item], update_modified=False)
	for name, package in frappe.get_all("Solar Design Estimate", filters={"bom_basis": ["is", "set"]},
			fields=["name", "solar_package"], as_list=True):
		if not package or not frappe.db.exists("Solar Package", package):
			continue
		estimate = frappe.get_doc("Solar Design Estimate", name)
		basis = estimate.bom_basis_for(frappe.get_cached_doc("Solar Package", package))
		frappe.db.set_value("Solar Design Estimate", name, "bom_basis", basis, update_modified=False)
