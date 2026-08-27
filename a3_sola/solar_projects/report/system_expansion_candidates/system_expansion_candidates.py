# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""System Expansion Candidates.

Deliberately a report and not an automatic opportunity. Consumption grows for all sorts of
reasons - a new tenant, a bad summer, a faulty meter - and raising a sales opportunity off
a number the customer has not discussed would put the client in front of them with the
wrong conversation. This lists who is worth a call; a human decides.

Two independent signals:

* the consumer's recorded consumption has grown past what the installed capacity offsets;
* the Phase 1 site survey recorded usable roof the installed array never took up.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api import calculations


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Installation"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Installation", "width": 160},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("Installed kWp"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 120},
		{"label": _("Monthly Units"), "fieldname": "avg_consumption_units", "fieldtype": "Float", "precision": 0, "width": 120},
		{"label": _("Units Offset"), "fieldname": "offset_units", "fieldtype": "Float", "precision": 0, "width": 120},
		{"label": _("Shortfall Units"), "fieldname": "shortfall_units", "fieldtype": "Float", "precision": 0, "width": 130},
		{"label": _("Capacity Gap kWp"), "fieldname": "capacity_gap_kw", "fieldtype": "Float", "precision": 2, "width": 150},
		{"label": _("Unused Roof kWp"), "fieldname": "unused_roof_kw", "fieldtype": "Float", "precision": 2, "width": 140},
		{"label": _("Headroom kWp"), "fieldname": "headroom_kw", "fieldtype": "Float", "precision": 2, "width": 130},
		{"label": _("Why"), "fieldname": "reason", "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	installations = frappe.get_list(
		"Solar Installation",
		filters={"company": filters.company, "docstatus": 1, "project": ["is", "set"]},
		fields=["name", "solar_consumer", "capacity_kw", "solar_design_estimate"],
		limit_page_length=0,
	)
	out = []
	for row in installations:
		consumer = frappe.db.get_value(
			"Solar Consumer", row.solar_consumer, ["avg_consumption_units"], as_dict=True
		)
		row["avg_consumption_units"] = flt(consumer.avg_consumption_units) if consumer else 0.0

		monthly = calculations.estimate_generation(row.capacity_kw)["annual_generation_kwh"] / 12.0
		row["offset_units"] = flt(monthly, 0)
		row["shortfall_units"] = flt(max(row["avg_consumption_units"] - monthly, 0), 0)
		row["capacity_gap_kw"] = (
			flt(row["shortfall_units"] * row.capacity_kw / monthly, 2) if monthly else 0.0
		)
		row["unused_roof_kw"] = _unused_roof(row.solar_design_estimate, row.capacity_kw)
		row["headroom_kw"] = flt(min(row["capacity_gap_kw"], row["unused_roof_kw"]), 2)

		reasons = []
		if row["capacity_gap_kw"] >= 0.5:
			reasons.append(_("consumption has grown past what the array offsets"))
		if row["unused_roof_kw"] >= 0.5:
			reasons.append(_("the survey recorded usable roof the array never took up"))
		if not reasons:
			continue
		row["reason"] = "; ".join(reasons).capitalize()
		out.append(row)

	out.sort(key=lambda r: (r["headroom_kw"], r["capacity_gap_kw"]), reverse=True)
	return out


def _unused_roof(estimate, installed_kw):
	"""Roof the Phase 1 survey said would take an array, less what actually went on it.

	`roof_limited_capacity_kw` is what the survey measured the roof could hold. Where the
	final capacity came out lower - budget, subsidy cap, a shaded segment left out - that
	difference is roof the client has already surveyed and can quote against tomorrow.
	"""
	if not estimate:
		return 0.0
	roof = flt(frappe.db.get_value("Solar Design Estimate", estimate, "roof_limited_capacity_kw"))
	return flt(max(roof - flt(installed_kw), 0), 2)
