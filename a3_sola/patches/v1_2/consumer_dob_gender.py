# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer's date of birth and gender, as on the Aadhaar card (api/aadhaar_card.py)."""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_consumer")
