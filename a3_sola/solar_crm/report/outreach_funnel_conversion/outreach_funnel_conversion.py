# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Outreach Funnel Conversion.

Cadence step against lead status, so the client can see whether step 3 or step 4 is
actually closing anything - which their spreadsheet could not tell them."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(filters), get_data(filters)


STEPS = [
	"Step 1: First Contact",
	"Step 2: 24hr Nudge",
	"Step 3: Value/ROI",
	"Step 4: Breakup/Close",
	"Completed: Proposal Sent",
]
STATUSES = [
	"New", "Contacted", "In Discussion", "Site Visit Scheduled",
	"Converted / Won", "Closed / Unresponsive", "Not Interested",
]


def get_columns(filters):
	columns = [{"label": _("Outreach Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 180}]
	for status in STATUSES:
		columns.append({"label": _(status), "fieldname": frappe.scrub(status), "fieldtype": "Int", "width": 120})
	columns.append({"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 90})
	columns.append({"label": _("Total kW"), "fieldname": "total_kw", "fieldtype": "Float", "precision": 2, "width": 100})
	columns.append({"label": _("Won %"), "fieldname": "won_percent", "fieldtype": "Percent", "width": 90})
	return columns


def get_data(filters):
	conditions = {"company": filters.company}
	if filters.get("from_date"):
		conditions["creation"] = [">=", filters.from_date]
	leads = frappe.get_list(
		"Lead",
		filters=conditions,
		fields=["outreach_stage", "solar_lead_status", "approx_capacity_kw"],
		limit_page_length=0,
	)

	rows = []
	for stage in STEPS:
		bucket = [l for l in leads if l.outreach_stage == stage]
		row = {"stage": stage, "total": len(bucket)}
		row["total_kw"] = flt(sum(flt(l.approx_capacity_kw) for l in bucket), 2)
		for status in STATUSES:
			row[frappe.scrub(status)] = len([l for l in bucket if l.solar_lead_status == status])
		won = row.get(frappe.scrub("Converted / Won"), 0)
		row["won_percent"] = flt(won * 100.0 / len(bucket), 2) if bucket else 0
		rows.append(row)
	return rows
