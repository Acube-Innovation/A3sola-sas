# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Each package's prices move to its Pricing Options: a row for each inverter option priced
the old way - on its panel, with the default battery, at its Cost (the default inverter's at
the Package Cost when it had none). Written straight to the rows, no package is re-saved, and
every price stays as it was."""

import frappe
from frappe.utils import flt


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package_pricing_option")
	frappe.reload_doc("solar_crm", "doctype", "solar_package_inverter")
	frappe.reload_doc("solar_crm", "doctype", "solar_package")
	from a3_sola.solar_crm.doctype.solar_package.solar_package import _default_row

	for name in frappe.get_all("Solar Package", pluck="name"):
		doc = frappe.get_doc("Solar Package", name)
		if doc.get("pricing_options"):
			continue
		doc.seed_pricing_options()
		rows = doc.get("pricing_options") or []
		if rows and not any(r.is_default for r in rows):
			rows[0].is_default = 1
		for idx, row in enumerate(rows, start=1):
			row.idx = idx
			row.db_insert()
		default = _default_row(doc, "pricing_options")
		if default and flt(default.cost):
			frappe.db.set_value("Solar Package", name, "package_cost", flt(default.cost), update_modified=False)
