# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's BOM tab holds only the rows typed or uploaded into it (package_bom_tree): the rows a
save copied in from the package's other tabs, and the items it listed under a bundle or BOM row,
are taken out - written straight to the tables, no package re-saved - the rest renumbered in their
order, and each package's Expenses total follows its rows."""

import frappe
from frappe.utils import flt

TABLES = ("Solar Package Material BOM", "Solar Package Structure BOM", "Solar Package Expense")


def execute():
	for child in TABLES:
		if not frappe.db.has_column(child, "source_row"):
			continue
		frappe.db.sql(f"""delete from `tab{child}` where parenttype = 'Solar Package'
			and (ifnull(source_row, '') != '' or row_kind = 'Component')""")
		frappe.db.sql(f"update `tab{child}` set row_kind = null, bom_no = null where parenttype = 'Solar Package'")
		for parent, parentfield in frappe.db.sql(f"select distinct parent, parentfield from `tab{child}` where parenttype = 'Solar Package'"):
			names = frappe.get_all(child, filters={"parent": parent, "parentfield": parentfield, "parenttype": "Solar Package"},
				order_by="idx asc", pluck="name")
			for idx, name in enumerate(names, start=1):
				frappe.db.set_value(child, name, "idx", idx, update_modified=False)
	for name in frappe.get_all("Solar Package", pluck="name"):
		total = frappe.db.sql("""select sum(amount) from `tabSolar Package Expense`
			where parent = %s and parenttype = 'Solar Package'""", name)[0][0]
		frappe.db.set_value("Solar Package", name, "total_expenses", flt(total), update_modified=False)
