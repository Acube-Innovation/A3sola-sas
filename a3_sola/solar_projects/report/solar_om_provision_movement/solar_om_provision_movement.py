# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""O&M Provision Movement.

The five-year obligation is a liability from the day of commissioning. This shows what was
set aside against it, what has been consumed, and how far into the term that consumption is
- a contract two years in with a nearly untouched provision is not good news, it usually
means visits are not happening.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Solar OM Contract", "width": 150},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 140},
		{"label": _("Start"), "fieldname": "start_date", "fieldtype": "Date", "width": 100},
		{"label": _("End"), "fieldname": "end_date", "fieldtype": "Date", "width": 100},
		{"label": _("Allocated"), "fieldname": "om_provision_allocated", "fieldtype": "Currency", "width": 120},
		{"label": _("Consumed"), "fieldname": "consumed", "fieldtype": "Currency", "width": 120},
		{"label": _("Balance"), "fieldname": "om_provision_balance", "fieldtype": "Currency", "width": 120},
		{"label": _("Consumed %"), "fieldname": "consumed_percent", "fieldtype": "Percent", "width": 120},
		{"label": _("Term Elapsed %"), "fieldname": "term_elapsed_percent", "fieldtype": "Percent", "width": 140},
		{"label": _("Drift"), "fieldname": "drift", "fieldtype": "Percent", "width": 100},
		{"label": _("Years Remaining"), "fieldname": "years_remaining", "fieldtype": "Float", "precision": 1, "width": 140},
		{"label": _("Balance per Remaining Year"), "fieldname": "balance_per_year", "fieldtype": "Currency", "width": 210},
		{"label": _("Coverage Ratio"), "fieldname": "coverage_ratio", "fieldtype": "Float", "precision": 2, "width": 140},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Solar OM Contract",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "project", "start_date", "end_date", "om_provision_allocated",
			"om_provision_balance",
		],
		limit_page_length=0,
	)
	for row in rows:
		allocated = flt(row.om_provision_allocated)
		row["consumed"] = flt(allocated - flt(row.om_provision_balance), 2)
		row["consumed_percent"] = flt(row["consumed"] * 100.0 / allocated, 2) if allocated else 0.0

		total_days = date_diff(row.end_date, row.start_date) or 1
		elapsed = min(max(date_diff(today(), row.start_date), 0), total_days)
		row["term_elapsed_percent"] = flt(elapsed * 100.0 / total_days, 2)
		# Positive drift means the provision is being spent faster than the term is running.
		row["drift"] = flt(row["consumed_percent"] - row["term_elapsed_percent"], 2)

		# What is left, against what is left to serve. A coverage ratio below 1 means the
		# provision will not see the obligation out at the current burn rate.
		remaining_days = max(total_days - elapsed, 0)
		row["years_remaining"] = flt(remaining_days / 365.0, 1)
		row["balance_per_year"] = (
			flt(flt(row.om_provision_balance) / row["years_remaining"], 2)
			if row["years_remaining"]
			else 0.0
		)
		burn_per_year = (
			flt(row["consumed"] / (elapsed / 365.0), 2) if elapsed >= 30 else 0.0
		)
		row["coverage_ratio"] = (
			flt(row["balance_per_year"] / burn_per_year, 2) if burn_per_year else 0.0
		)
	rows.sort(key=lambda r: r["drift"], reverse=True)
	return rows
