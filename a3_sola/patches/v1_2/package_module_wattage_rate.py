# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A panel option's Rate per Panel is its Wattage x Wattage Rate. A row with a rate and a wattage
gets the Wattage Rate that makes its rate again - where one to the paisa does, so no rate moves;
any other row keeps its Rate per Panel until a Wattage Rate is given."""

import frappe
from frappe.utils import flt


def execute():
	for row in frappe.get_all("Solar Package Module", filters={"wattage_rate": ["in", [0, None]], "bundle_part": ["in", [0, None]]},
			fields=["name", "rate", "module_wattage"]):
		watts, rate = flt(row.module_wattage), flt(row.rate)
		if not (watts and rate):
			continue
		per_watt = flt(rate / watts, 2)
		if abs(per_watt * watts - rate) < 0.005:
			frappe.db.set_value("Solar Package Module", row.name, "wattage_rate", per_watt, update_modified=False)
