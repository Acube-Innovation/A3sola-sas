# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""GST rounded as the suppliers' tax invoices round it, so a bill entered on the Supplier
Invoice task (api/supplier_bill) comes to the paisa it says: each line's tax rounded on its own
("Round Tax Amount Row-wise"), and half a paisa rounded up ("Commercial Rounding") - RIM's
RPVT/26-27/6377 is CGST and SGST 8,713.69 each that way, 8,713.68 rounded once on the total.

Chosen for the whole site, sales and purchases alike."""

import frappe


def execute():
	frappe.db.set_single_value("Accounts Settings", "round_row_wise_tax", 1)
	if "Commercial Rounding" in (frappe.get_meta("System Settings").get_field("rounding_method").options or ""):
		frappe.db.set_single_value("System Settings", "rounding_method", "Commercial Rounding")
	frappe.clear_cache()
