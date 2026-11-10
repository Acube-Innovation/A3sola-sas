# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Each package inverter option's new Item Group and Inverter Amount, as a save would set them: the
group its Item is in (one of the Inverters groups), and its Rate per Inverter times Nos. Written
straight to the rows; no package is re-saved."""

import frappe
from frappe.utils import cint, flt

from a3_sola.solar_crm.doctype.solar_package.solar_package import inverter_groups


def execute():
	groups = inverter_groups()
	for row in frappe.get_all("Solar Package Inverter", filters={"parenttype": "Solar Package"},
			fields=["name", "inverter_item", "unit_rate", "inverter_count"]):
		values = {"amount": flt(row.unit_rate) * cint(row.inverter_count)}
		group = frappe.db.get_value("Item", row.inverter_item, "item_group") if row.inverter_item else None
		if group in groups:
			values["item_group"] = group
		frappe.db.set_value("Solar Package Inverter", row.name, values, update_modified=False)
