# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Proposal Register.

The client's proposal spreadsheet, reproduced column for column so nothing is lost in the
migration - their bankers ask for this listing by name."""

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
		{"label": _("Proposal No"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Proposal", "width": 175},
		{"label": _("Sl"), "fieldname": "proposal_sequence", "fieldtype": "Int", "width": 60},
		{"label": _("Date"), "fieldname": "proposal_date", "fieldtype": "Date", "width": 100},
		{"label": _("Salutation"), "fieldname": "salutation", "fieldtype": "Data", "width": 90},
		{"label": _("Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 170},
		{"label": _("Mobile"), "fieldname": "mobile_no", "fieldtype": "Data", "width": 120},
		{"label": _("Capacity"), "fieldname": "capacity_label", "fieldtype": "Data", "width": 150},
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Data", "width": 150},
		{"label": _("Options"), "fieldname": "options_quoted", "fieldtype": "Int", "width": 80},
		{"label": _("Quoted"), "fieldname": "recommended_option_cost", "fieldtype": "Currency", "width": 130},
		{"label": _("File Name"), "fieldname": "proposal_file_name", "fieldtype": "Data", "width": 340},
		{"label": _("Sent Via"), "fieldname": "sent_via", "fieldtype": "Data", "width": 100},
		{"label": _("Sent On"), "fieldname": "sent_on", "fieldtype": "Datetime", "width": 150},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	conditions = {"company": filters.company, "docstatus": ["<", 2]}
	if filters.get("fiscal_year"):
		conditions["fiscal_year"] = filters.fiscal_year
	if filters.get("status"):
		conditions["status"] = filters.status
	return frappe.get_list(
		"Solar Proposal",
		filters=conditions,
		fields=[
			"name", "proposal_sequence", "proposal_date", "salutation", "customer_name",
			"mobile_no", "capacity_label", "location", "options_quoted",
			"recommended_option_cost", "proposal_file_name", "sent_via", "sent_on", "status",
		],
		order_by="proposal_date desc, proposal_sequence desc",
		limit_page_length=0,
	)
