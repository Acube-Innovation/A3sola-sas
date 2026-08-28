# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""O&M Contract Register.

The obligation register. Everything the client has committed to maintain, with the warranty
terms as they actually stand for each site rather than a house figure.
"""

import frappe
from frappe import _
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Solar OM Contract", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("kWp"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Type"), "fieldname": "contract_type", "fieldtype": "Data", "width": 200},
		{"label": _("Start"), "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": _("End"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Module Make"), "fieldname": "module_make", "fieldtype": "Link", "options": "Component Make", "width": 130},
		{"label": _("Module Product Yrs"), "fieldname": "module_product_warranty_years", "fieldtype": "Int", "width": 150},
		{"label": _("Module Perf. Yrs"), "fieldname": "module_performance_warranty_years", "fieldtype": "Int", "width": 140},
		{"label": _("Inverter Make"), "fieldname": "inverter_make", "fieldtype": "Link", "options": "Component Make", "width": 130},
		{"label": _("Inverter Yrs"), "fieldname": "inverter_warranty_years", "fieldtype": "Int", "width": 110},
		{"label": _("Scheme Mandated"), "fieldname": "is_scheme_mandated", "fieldtype": "Check", "width": 140},
	]


def get_data(filters):
	return frappe.get_list(
		"Solar OM Contract",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "solar_consumer", "capacity_kw", "contract_type", "start_date", "end_date",
			"status", "module_make", "module_product_warranty_years",
			"module_performance_warranty_years", "inverter_make", "inverter_warranty_years",
			"is_scheme_mandated",
		],
		order_by="end_date asc",
		limit_page_length=0,
	)
