# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Renewal Pipeline.

A contract coming to the end of its five years is the client's warmest sales lead: the site
is known, the performance history is in the system, and the relationship already exists.
Visit compliance and open tickets sit alongside the expiry date because those are what the
conversation will actually turn on.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Solar OM Contract", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("kWp"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Expires"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 130},
		{"label": _("Visit Compliance %"), "fieldname": "visit_compliance_percent", "fieldtype": "Percent", "width": 160},
		{"label": _("Open Tickets"), "fieldname": "open_tickets", "fieldtype": "Int", "width": 120},
		{"label": _("Current PR"), "fieldname": "current_performance_ratio_percent", "fieldtype": "Percent", "width": 120},
		{"label": _("Opportunity"), "fieldname": "opportunity", "fieldtype": "Link", "options": "Opportunity", "width": 150},
	]


def get_data(filters):
	window = frappe.db.get_single_value("A3 Sola Settings", "contract_expiry_window_days") or 90
	rows = frappe.get_list(
		"Solar OM Contract",
		filters={
			"company": filters.company,
			"docstatus": 1,
			"status": ["not in", ["Renewed", "Terminated"]],
			"end_date": ["<=", frappe.utils.add_days(today(), int(window))],
		},
		fields=[
			"name", "solar_consumer", "capacity_kw", "end_date", "visit_compliance_percent",
			"open_tickets", "current_performance_ratio_percent",
		],
		order_by="end_date asc",
		limit_page_length=0,
	)
	for row in rows:
		row["days_to_expiry"] = date_diff(getdate(row.end_date), today())
		row["opportunity"] = frappe.db.get_value("Opportunity", {"om_contract": row.name}, "name")
	return rows
