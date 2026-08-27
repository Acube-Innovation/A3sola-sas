# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Project Profitability.

Margin is measured against what was actually billed, and statutory pass-through is shown
in its own column so it can never be mistaken for either cost or revenue.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Project"), "fieldname": "name", "fieldtype": "Link", "options": "Project", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("kWp"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Contract Value"), "fieldname": "gross_contract_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Billed"), "fieldname": "total_billed_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Collected"), "fieldname": "total_collected_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Total Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin"), "fieldname": "gross_margin_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin %"), "fieldname": "gross_margin_percent", "fieldtype": "Percent", "width": 100},
		{"label": _("Cost / kWp"), "fieldname": "cost_per_kw", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin / kWp"), "fieldname": "margin_per_kw", "fieldtype": "Currency", "width": 120},
		{"label": _("Statutory Pass-Through"), "fieldname": "statutory_pass_through", "fieldtype": "Currency", "width": 170},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Project",
		filters={"company": filters.company, "solar_installation": ["is", "set"]},
		fields=[
			"name", "solar_consumer", "capacity_kw", "gross_contract_value",
			"total_billed_amount", "total_collected_amount", "total_cost",
			"gross_margin_amount", "gross_margin_percent", "cost_per_kw", "margin_per_kw",
			"statutory_pass_through",
		],
		order_by="gross_margin_percent asc",
		limit_page_length=0,
	)
	return [row for row in rows if flt(row.gross_contract_value) or flt(row.total_cost)]
