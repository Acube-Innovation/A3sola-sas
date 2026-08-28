# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Lead Follow-up Due.

The report the sales team opens first every morning. It replaces the conditional
formatting in the client's lead tracker: a lead past its next follow-up date, with
everything needed to make the call without opening the record."""

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
		{"label": _("Lead"), "fieldname": "name", "fieldtype": "Link", "options": "Lead", "width": 130},
		{"label": _("Customer"), "fieldname": "lead_name", "fieldtype": "Data", "width": 160},
		{"label": _("Phone"), "fieldname": "mobile_no", "fieldtype": "Data", "width": 120},
		{"label": _("Location"), "fieldname": "city", "fieldtype": "Data", "width": 120},
		{"label": _("Avg Monthly Bill"), "fieldname": "avg_monthly_bill", "fieldtype": "Currency", "width": 130},
		{"label": _("Size (kW)"), "fieldname": "approx_capacity_kw", "fieldtype": "Float", "precision": 2, "width": 90},
		{"label": _("Call Status"), "fieldname": "call_status", "fieldtype": "Data", "width": 120},
		{"label": _("Outreach Stage"), "fieldname": "outreach_stage", "fieldtype": "Data", "width": 170},
		{"label": _("Lead Status"), "fieldname": "solar_lead_status", "fieldtype": "Data", "width": 150},
		{"label": _("Last Message"), "fieldname": "last_message_date", "fieldtype": "Date", "width": 110},
		{"label": _("Next Follow-up"), "fieldname": "next_followup_date", "fieldtype": "Date", "width": 120},
		{"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 110},
		{"label": _("Owner"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 160},
	]


def get_data(filters):
	conditions = {"company": filters.company, "status": ["not in", ["Converted", "Do Not Contact"]]}
	if filters.get("owner"):
		conditions["owner"] = filters.owner
	if filters.get("only_due"):
		conditions["followup_status"] = "FOLLOW UP DUE"

	rows = frappe.get_list(
		"Lead",
		filters=conditions,
		fields=[
			"name", "lead_name", "mobile_no", "city", "avg_monthly_bill", "approx_capacity_kw",
			"call_status", "outreach_stage", "solar_lead_status", "last_message_date",
			"next_followup_date", "followup_status", "owner",
		],
		order_by="next_followup_date asc",
		limit_page_length=0,
	)
	for row in rows:
		row["days_overdue"] = (
			frappe.utils.date_diff(today(), row.next_followup_date) if row.next_followup_date else 0
		)
	return rows
