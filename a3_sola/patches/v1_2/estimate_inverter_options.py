# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Draft design estimates carry every inverter alternative of their package as an option.

Estimates used to be seeded with the package's default inverter only. Each draft whose
options all came from its package is saved once, which rewrites them from the package. One
that fails to save is logged and left as it was; it is brought up to date on its next save.
"""

import frappe


def execute():
	for name in frappe.get_all("Solar Design Estimate", filters={"docstatus": 0}, pluck="name"):
		doc = frappe.get_doc("Solar Design Estimate", name)
		if not doc.solar_package or any(row.component_make for row in doc.options):
			continue
		try:
			doc.flags.ignore_permissions = True
			doc.save()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"estimate_inverter_options: {name} skipped")
		else:
			frappe.db.commit()
