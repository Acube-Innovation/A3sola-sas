# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Installation Pipeline Status.

The daily standup report: every open job, the stage it is on, who owns that stage and how
long it has been there."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Installation"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Installation", "width": 150},
		{"label": _("Consumer"), "fieldname": "consumer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Current Stage"), "fieldname": "current_stage", "fieldtype": "Data", "width": 180},
		{"label": _("Stage Owner"), "fieldname": "current_stage_owner_type", "fieldtype": "Data", "width": 110},
		{"label": _("Days in Stage"), "fieldname": "days_in_stage", "fieldtype": "Int", "width": 110},
		{"label": _("SLA"), "fieldname": "sla_days", "fieldtype": "Int", "width": 70},
		{"label": _("Breached"), "fieldname": "is_sla_breached", "fieldtype": "Check", "width": 80},
		{"label": _("Blocking Party"), "fieldname": "blocking_party", "fieldtype": "Data", "width": 120},
		{"label": _("Progress"), "fieldname": "overall_progress_percent", "fieldtype": "Percent", "width": 90},
		{"label": _("Capacity (kW)"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 110},
		{"label": _("Contract Value"), "fieldname": "gross_contract_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Section"), "fieldname": "discom_section", "fieldtype": "Link", "options": "DISCOM Section", "width": 130},
		{"label": _("Project Manager"), "fieldname": "project_manager", "fieldtype": "Link", "options": "User", "width": 150},
	]


def get_data(filters):
	conditions = {"company": filters.company, "docstatus": 1,
	              "status": ["not in", ["Closed", "Cancelled"]]}
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("discom_section"):
		conditions["discom_section"] = filters.discom_section
	if filters.get("breached_only"):
		conditions["is_sla_breached"] = 1

	rows = frappe.get_list(
		"Solar Installation",
		filters=conditions,
		fields=[
			"name", "consumer_name", "current_stage", "current_stage_owner_type",
			"is_sla_breached", "blocking_party", "overall_progress_percent", "capacity_kw",
			"gross_contract_value", "discom_section", "project_manager",
		],
		limit_page_length=0,
	)
	for row in rows:
		current = frappe.db.get_value(
			"Installation Stage Log",
			{"parent": row.name, "status": ["in", ["In Progress", "Blocked"]]},
			["days_in_stage", "sla_days"],
			as_dict=True,
			order_by="idx asc",
		)
		row["days_in_stage"] = current.days_in_stage if current else 0
		row["sla_days"] = current.sla_days if current else 0
	return rows
