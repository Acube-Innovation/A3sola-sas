# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Stage Cycle Time Analysis.

Average, median and 90th percentile days per stage against the SLA. Use it to re-baseline
the stage template after six months of live data, rather than guessing again."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today
from a3_sola.api.permissions import resolve_report_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Not simply what the caller asked for - see permissions.resolve_report_company.
	filters.company = resolve_report_company(filters.company)
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Stage"), "fieldname": "stage_name", "fieldtype": "Data", "width": 210},
		{"label": _("Owner"), "fieldname": "owner_type", "fieldtype": "Data", "width": 110},
		{"label": _("Completed"), "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": _("SLA"), "fieldname": "sla_days", "fieldtype": "Int", "width": 70},
		{"label": _("Average"), "fieldname": "avg_days", "fieldtype": "Float", "precision": 1, "width": 90},
		{"label": _("Median"), "fieldname": "median_days", "fieldtype": "Float", "precision": 1, "width": 90},
		{"label": _("90th %ile"), "fieldname": "p90_days", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Over SLA"), "fieldname": "over_sla", "fieldtype": "Int", "width": 90},
		{"label": _("Suggested SLA"), "fieldname": "suggested_sla", "fieldtype": "Int", "width": 120},
	]


def get_data(filters):
	rows = frappe.db.sql(
		"""
		select log.stage_code, log.stage_name, log.owner_type, log.sla_days, log.days_in_stage
		from `tabInstallation Stage Log` log
		join `tabSolar Installation` inst on inst.name = log.parent
		where inst.company = %(company)s and inst.docstatus = 1
		  and log.status = 'Completed' and log.days_in_stage is not null
		""",
		{"company": filters.company},
		as_dict=True,
	)

	buckets = {}
	for row in rows:
		bucket = buckets.setdefault(
			row.stage_code,
			{"stage_name": row.stage_name, "owner_type": row.owner_type,
			 "sla_days": row.sla_days, "days": []},
		)
		bucket["days"].append(flt(row.days_in_stage))

	out = []
	for bucket in buckets.values():
		days = sorted(bucket.pop("days"))
		if not days:
			continue
		bucket["completed"] = len(days)
		bucket["avg_days"] = flt(sum(days) / len(days), 1)
		bucket["median_days"] = flt(days[len(days) // 2], 1)
		bucket["p90_days"] = flt(days[max(int(len(days) * 0.9) - 1, 0)], 1)
		bucket["over_sla"] = len([d for d in days if d > flt(bucket["sla_days"])])
		# A defensible re-baseline: cover 90% of observed reality.
		bucket["suggested_sla"] = int(bucket["p90_days"]) or bucket["sla_days"]
		out.append(bucket)
	return sorted(out, key=lambda r: -r["avg_days"])
