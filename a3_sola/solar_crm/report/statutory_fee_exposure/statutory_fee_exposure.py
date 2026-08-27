# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Statutory Fee Exposure.

What every open job will cost the customer in DISCOM charges, and how much of it comes
back. The client currently has no view of this number at all."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Design Estimate"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Design Estimate", "width": 170},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("Capacity (kW)"), "fieldname": "final_capacity_kw", "fieldtype": "Float", "precision": 2, "width": 110},
		{"label": _("Net Meter"), "fieldname": "net_meter_mode", "fieldtype": "Data", "width": 190},
		{"label": _("Application Fee"), "fieldname": "kseb_application_fee", "fieldtype": "Currency", "width": 130},
		{"label": _("Registration Fee"), "fieldname": "kseb_registration_fee", "fieldtype": "Currency", "width": 140},
		{"label": _("Refundable"), "fieldname": "kseb_registration_refundable", "fieldtype": "Currency", "width": 120},
		{"label": _("Net Meter Charge"), "fieldname": "net_meter_charge", "fieldtype": "Currency", "width": 140},
		{"label": _("Total"), "fieldname": "statutory_total", "fieldtype": "Currency", "width": 130},
		{"label": _("Net of Refund"), "fieldname": "net_of_refund", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Solar Design Estimate",
		filters={"company": filters.company, "docstatus": ["<", 2]},
		fields=[
			"name", "solar_consumer", "final_capacity_kw", "net_meter_mode",
			"kseb_application_fee", "kseb_registration_fee", "kseb_registration_refundable",
			"net_meter_charge", "statutory_total",
		],
		order_by="creation desc",
		limit_page_length=0,
	)
	for row in rows:
		row["net_of_refund"] = flt(row.statutory_total) - flt(row.kseb_registration_refundable)
	return rows
