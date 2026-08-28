# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Solar Sales Pipeline.

One row per Solar Consumer with the stage it has reached and how long it has been there."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Consumer"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Consumer", "width": 160},
		{"label": _("Name"), "fieldname": "consumer_name", "fieldtype": "Data", "width": 170},
		{"label": _("Category"), "fieldname": "consumer_category", "fieldtype": "Data", "width": 110},
		{"label": _("Stage"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Days in Stage"), "fieldname": "days_in_stage", "fieldtype": "Int", "width": 110},
		{"label": _("Capacity (kW)"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 110},
		{"label": _("Estimated Value"), "fieldname": "estimated_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Section"), "fieldname": "discom_section", "fieldtype": "Link", "options": "DISCOM Section", "width": 140},
		{"label": _("Owner"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 160},
	]


def get_data(filters):
	conditions = {"company": filters.company}
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("consumer_category"):
		conditions["consumer_category"] = filters.consumer_category
	if filters.get("discom_section"):
		conditions["discom_section"] = filters.discom_section

	rows = frappe.get_list(
		"Solar Consumer",
		filters=conditions,
		fields=["name", "consumer_name", "consumer_category", "status", "discom_section", "owner", "modified"],
		limit_page_length=0,
	)
	for row in rows:
		row["days_in_stage"] = frappe.utils.date_diff(today(), getdate(row.modified))
		estimate = frappe.db.get_value(
			"Solar Design Estimate",
			{"solar_consumer": row.name, "docstatus": ["<", 2]},
			["final_capacity_kw", "total_project_cost"],
			as_dict=True,
			order_by="creation desc",
		)
		row["capacity_kw"] = flt(estimate.final_capacity_kw) if estimate else 0
		row["estimated_value"] = flt(estimate.total_project_cost) if estimate else 0
	return rows
