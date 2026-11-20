# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Estimates drop the Optional Add-ons they were given automatically - from their package,
or the inverter warranty extension - as packages no longer offer any (clear_package_add_ons).
They were offered, never priced, so no estimate's total changes. An add-on is entered on the
estimate when wanted. Rows an estimate kept from the add-ons table it had before go too."""

import frappe


def execute():
	frappe.db.delete("Design Estimate Add-on", {"parenttype": "Solar Design Estimate", "is_option": 1})
	frappe.db.delete("Solar Package Add-on", {"parenttype": "Solar Design Estimate"})
