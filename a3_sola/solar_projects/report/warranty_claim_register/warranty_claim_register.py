# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Warranty Claim Register.

Every claim traces to a serial in the installation's register, and the applicable term is
this make's own - a Rayzon module and a Vikram module on adjacent roofs expire three years
apart, so a single house figure would misstate half the register.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Claim"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Warranty Claim", "width": 150},
		{"label": _("Installation"), "fieldname": "solar_installation", "fieldtype": "Link", "options": "Solar Installation", "width": 160},
		{"label": _("Component"), "fieldname": "component_type", "fieldtype": "Data", "width": 110},
		{"label": _("Make"), "fieldname": "component_make", "fieldtype": "Link", "options": "Component Make", "width": 120},
		{"label": _("Serial"), "fieldname": "serial_no", "fieldtype": "Data", "width": 160},
		{"label": _("Failed"), "fieldname": "failure_date", "fieldtype": "Date", "width": 100},
		{"label": _("Basis"), "fieldname": "claim_basis", "fieldtype": "Data", "width": 110},
		{"label": _("Term Yrs"), "fieldname": "warranty_years_applicable", "fieldtype": "Int", "width": 100},
		{"label": _("Expires"), "fieldname": "warranty_expiry_date", "fieldtype": "Date", "width": 100},
		{"label": _("In Warranty"), "fieldname": "is_within_warranty", "fieldtype": "Check", "width": 110},
		{"label": _("Status"), "fieldname": "claim_status", "fieldtype": "Data", "width": 120},
		{"label": _("Replacement"), "fieldname": "replacement_serial_no", "fieldtype": "Data", "width": 150},
		{"label": _("Claim Value"), "fieldname": "claim_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Recovered"), "fieldname": "amount_recovered", "fieldtype": "Currency", "width": 120},
		{"label": _("Borne by Company"), "fieldname": "cost_borne_by_company", "fieldtype": "Currency", "width": 160},
		{"label": _("Days with Manufacturer"), "fieldname": "days_open", "fieldtype": "Int", "width": 180},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Solar Warranty Claim",
		filters={"company": filters.company, "docstatus": ["<", 2]},
		fields=[
			"name", "solar_installation", "component_type", "component_make", "manufacturer",
			"serial_no", "failure_date", "claim_basis", "warranty_years_applicable",
			"warranty_expiry_date", "is_within_warranty", "claim_status",
			"replacement_serial_no", "claim_value", "amount_recovered",
			"cost_borne_by_company", "claim_submitted_on", "replacement_received_on",
		],
		limit_page_length=0,
	)
	settled = ("Replaced", "Rejected", "Closed")
	for row in rows:
		# How long the manufacturer has had it. A claim ageing past a quarter is a claim
		# the client needs to chase, not a claim in progress.
		if row.claim_status in settled:
			end = row.replacement_received_on or today()
		else:
			end = today()
		row["days_open"] = (
			date_diff(getdate(end), getdate(row.claim_submitted_on)) if row.claim_submitted_on else 0
		)
	# Grouped by make so a bad batch reads as one block, oldest claim first within it.
	rows.sort(key=lambda r: (r.get("component_make") or "", -flt(r["days_open"])))
	return rows
