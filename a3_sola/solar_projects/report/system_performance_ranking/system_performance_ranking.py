# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""System Performance Ranking.

Two thresholds, and they mean different things. The operational threshold is a service
signal. The contractual floor is a clause in a signed agreement, and a system below it is
an exposure - so the obligation status is its own column, not a colour on the ratio.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

from a3_sola.api import calculations


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
		{"label": _("Age (years)"), "fieldname": "age_years", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("PR at Commissioning"), "fieldname": "performance_ratio_at_commissioning", "fieldtype": "Percent", "width": 170},
		{"label": _("Current PR"), "fieldname": "current_performance_ratio_percent", "fieldtype": "Percent", "width": 120},
		{"label": _("Contractual Floor"), "fieldname": "contractual_performance_ratio_percent", "fieldtype": "Percent", "width": 150},
		{"label": _("Headroom"), "fieldname": "headroom", "fieldtype": "Percent", "width": 110},
		{"label": _("Units / Day"), "fieldname": "actual_units_per_day", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("Quoted Band"), "fieldname": "quoted_band", "fieldtype": "Data", "width": 130},
		{"label": _("Against Quote"), "fieldname": "against_quote", "fieldtype": "Data", "width": 130},
		{"label": _("Obligation"), "fieldname": "performance_obligation_status", "fieldtype": "Data", "width": 120},
		{"label": _("Consecutive Low"), "fieldname": "consecutive_underperforming_readings", "fieldtype": "Int", "width": 150},
		{"label": _("Last Visit"), "fieldname": "last_visit", "fieldtype": "Date", "width": 110},
		{"label": _("Last Reading"), "fieldname": "last_reading", "fieldtype": "Date", "width": 120},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Solar OM Contract",
		filters={"company": filters.company, "docstatus": 1},
		fields=[
			"name", "solar_consumer", "solar_installation", "capacity_kw", "start_date",
			"performance_ratio_at_commissioning", "current_performance_ratio_percent",
			"contractual_performance_ratio_percent", "performance_obligation_status",
			"consecutive_underperforming_readings",
		],
		limit_page_length=0,
	)
	for row in rows:
		row["headroom"] = flt(
			flt(row.current_performance_ratio_percent)
			- flt(row.contractual_performance_ratio_percent),
			2,
		)
		row["age_years"] = (
			flt(date_diff(today(), getdate(row.start_date)) / 365.0, 1) if row.start_date else 0.0
		)
		row["last_visit"] = frappe.db.get_value(
			"Solar OM Visit", {"om_contract": row.name, "docstatus": 1}, "visit_date",
			order_by="visit_date desc",
		)

		# What the proposal actually promised: "20 to 25 units a day for a 5 kW system".
		# A customer complaint almost always starts as "it is not making what you said".
		band = calculations.estimate_daily_generation_band(row.capacity_kw)
		low, high = flt(band["low_units_per_day"], 1), flt(band["high_units_per_day"], 1)
		row["quoted_band"] = f"{low} - {high}"

		reading = frappe.db.get_value(
			"Generation Reading",
			{"solar_installation": row.solar_installation, "docstatus": 1},
			["reading_date", "units_generated_since_last", "days_since_last_reading"],
			order_by="reading_date desc",
			as_dict=True,
		)
		row["last_reading"] = None
		if reading:
			days = reading.days_since_last_reading or 1
			row["last_reading"] = reading.reading_date
			row["actual_units_per_day"] = flt(flt(reading.units_generated_since_last) / days, 1)
			row["against_quote"] = (
				_("Within band") if row["actual_units_per_day"] >= low else _("Below band")
			)
		else:
			row["actual_units_per_day"] = 0.0
			row["against_quote"] = _("No reading")

	# Worst first: the exposure is what needs reading, not the star performer.
	rows.sort(key=lambda r: r["headroom"])
	return rows
