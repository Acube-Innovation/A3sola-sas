# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""EHS & Feasibility Compliance.

The evidence pack a lender asks for, per job."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Survey"), "fieldname": "name", "fieldtype": "Link", "options": "Site Survey", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("Feasibility"), "fieldname": "feasibility_status", "fieldtype": "Data", "width": 160},
		{"label": _("EHS Status"), "fieldname": "ehs_overall_status", "fieldtype": "Data", "width": 170},
		{"label": _("Asbestos"), "fieldname": "asbestos_present", "fieldtype": "Check", "width": 90},
		{"label": _("Structural Cert"), "fieldname": "has_structural", "fieldtype": "Check", "width": 130},
		{"label": _("Owner Consent"), "fieldname": "owner_consent_obtained", "fieldtype": "Check", "width": 130},
		{"label": _("24x7 Access"), "fieldname": "roof_access_24x7", "fieldtype": "Check", "width": 110},
		{"label": _("Water Source"), "fieldname": "water_source_for_cleaning", "fieldtype": "Data", "width": 170},
		{"label": _("Conditions"), "fieldname": "ehs_conditions", "fieldtype": "Data", "width": 300},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Site Survey",
		filters={"company": filters.company, "docstatus": ["<", 2]},
		fields=[
			"name", "solar_consumer", "feasibility_status", "ehs_overall_status",
			"asbestos_present", "structural_safety_certificate", "owner_consent_obtained",
			"roof_access_24x7", "water_source_for_cleaning", "ehs_conditions",
		],
		limit_page_length=0,
	)
	for row in rows:
		row["has_structural"] = 1 if row.structural_safety_certificate else 0
	return rows
