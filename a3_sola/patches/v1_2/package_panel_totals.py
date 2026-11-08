# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Panel options get their Total Panel Rate (rate x nos) and packages their Total Package Cost
(solar_package.package_build_up), written straight to the rows so no package is re-saved and
no price moves."""

import frappe
from frappe.utils import flt


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package_module")
	frappe.reload_doc("solar_crm", "doctype", "solar_package")
	from a3_sola.solar_crm.doctype.solar_package.solar_package import package_build_up

	frappe.db.sql("""
		update `tabSolar Package Module`
		set amount = round(ifnull(rate, 0) * ifnull(module_count, 0), 2)
		where parenttype = 'Solar Package'""")
	frappe.db.sql("""
		update `tabDesign Estimate Battery`
		set amount = round(ifnull(rate, 0) * ifnull(nos, 0), 2)
		where parenttype = 'Solar Package'""")
	for name in frappe.get_all("Solar Package", pluck="name"):
		total = flt(package_build_up(frappe.get_doc("Solar Package", name))["total"], 2)
		frappe.db.set_value("Solar Package", name, "total_package_cost", total, update_modified=False)
