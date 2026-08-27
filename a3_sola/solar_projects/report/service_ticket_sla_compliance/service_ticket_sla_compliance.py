# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Service Ticket SLA Compliance.

The ministry's grievance framework permits temporary deactivation of a vendor that fails to
address consumer complaints, so this report exists to prove the client acted - which is why
escalation level and reopen count sit alongside the SLA flags rather than in a separate view.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime, time_diff_in_hours


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Ticket"), "fieldname": "name", "fieldtype": "Link", "options": "Service Ticket", "width": 150},
		{"label": _("Contract"), "fieldname": "om_contract", "fieldtype": "Link", "options": "Solar OM Contract", "width": 150},
		{"label": _("Severity"), "fieldname": "severity", "fieldtype": "Data", "width": 90},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 150},
		{"label": _("Reported"), "fieldname": "reported_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Response Met"), "fieldname": "response_sla_met", "fieldtype": "Check", "width": 120},
		{"label": _("Resolution Met"), "fieldname": "resolution_sla_met", "fieldtype": "Check", "width": 130},
		{"label": _("Hrs to Resolve"), "fieldname": "hours_to_resolution", "fieldtype": "Float", "precision": 1, "width": 130},
		{"label": _("Hrs Open"), "fieldname": "hours_open", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("Escalation"), "fieldname": "escalation_level", "fieldtype": "Int", "width": 100},
		{"label": _("Reopened"), "fieldname": "reopen_count", "fieldtype": "Int", "width": 100},
		{"label": _("Scheme Related"), "fieldname": "is_scheme_related", "fieldtype": "Check", "width": 140},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Service Ticket",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "om_contract", "severity", "category", "reported_on", "status",
			"response_sla_met", "resolution_sla_met", "hours_to_resolution", "resolved_on",
			"escalation_level", "reopen_count", "is_scheme_related",
		],
		order_by="reported_on desc",
		limit_page_length=0,
	)
	for row in rows:
		if row.status in ("Resolved", "Closed"):
			row["hours_open"] = flt(row.hours_to_resolution)
		elif row.reported_on:
			row["hours_open"] = flt(
				time_diff_in_hours(now_datetime(), get_datetime(row.reported_on)), 1
			)
		else:
			row["hours_open"] = 0.0
	return rows
