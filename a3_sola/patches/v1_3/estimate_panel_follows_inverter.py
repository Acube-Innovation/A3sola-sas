# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Design estimates made before an inverter brought its own panel: an option built on an
inverter its package pairs with another panel (Pricing Options) - a Hoymiles kit with its
550 Wp Rayzon - still prices the package's default panel. Draft estimates still on that
default panel move to the paired one; a panel ticked by hand on another row is left."""

import frappe

from a3_sola.solar_crm.doctype.solar_package.solar_package import default_module


def execute():
	for name in frappe.get_all("Solar Design Estimate", filters={"docstatus": 0, "solar_package": ["is", "set"]}, pluck="name"):
		try:
			doc = frappe.get_doc("Solar Design Estimate", name)
			row = doc.recommended_sizing_row()
			if not row or not row.solar_package:
				continue
			paired = doc.paired_panel_row(row)
			priced = next((r for r in doc.get("panels") or [] if not r.is_option), None)
			default = default_module(frappe.get_cached_doc("Solar Package", row.solar_package))
			if not (paired and priced and default) or paired is priced:
				continue
			on_default = (priced.panel_item and priced.panel_item == default.module_item) or (
				priced.panel_make == default.module_make and priced.panel_capacity_wp == default.module_wattage)
			if not on_default:
				continue
			for r in doc.panels:
				r.is_option = 0 if r is paired else 1
			row.panel_make = paired.panel_make
			doc.flags.ignore_permissions = True
			doc.save()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="Panel follows inverter patch: {0}".format(name))
		else:
			frappe.db.commit()
