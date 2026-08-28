# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""External Dependency Ageing.

Where working capital is trapped, and the evidence to escalate with the DISCOM. Grouped by
the party actually holding the job up - not by our own stage names."""

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
		{"label": _("Owner"), "fieldname": "owner_type", "fieldtype": "Data", "width": 120},
		{"label": _("Section"), "fieldname": "discom_section", "fieldtype": "Link", "options": "DISCOM Section", "width": 150},
		{"label": _("Stage"), "fieldname": "stage_name", "fieldtype": "Data", "width": 200},
		{"label": _("Jobs Waiting"), "fieldname": "jobs", "fieldtype": "Int", "width": 110},
		{"label": _("Avg Days"), "fieldname": "avg_days", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Max Days"), "fieldname": "max_days", "fieldtype": "Int", "width": 100},
		{"label": _("SLA"), "fieldname": "sla_days", "fieldtype": "Int", "width": 70},
		{"label": _("Breached"), "fieldname": "breached", "fieldtype": "Int", "width": 90},
		{"label": _("Capacity Held (kW)"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 150},
	]


def get_data(filters):
	rows = frappe.db.sql(
		"""
		select log.owner_type, log.stage_name, log.sla_days,
		       inst.discom_section, inst.capacity_kw, log.days_in_stage, log.is_sla_breached
		from `tabInstallation Stage Log` log
		join `tabSolar Installation` inst on inst.name = log.parent
		where inst.company = %(company)s
		  and inst.docstatus = 1
		  and log.status in ('In Progress', 'Blocked')
		  and log.owner_type != 'Internal'
		""",
		{"company": filters.company},
		as_dict=True,
	)

	buckets = {}
	for row in rows:
		key = (row.owner_type, row.discom_section, row.stage_name)
		bucket = buckets.setdefault(
			key,
			{
				"owner_type": row.owner_type,
				"discom_section": row.discom_section,
				"stage_name": row.stage_name,
				"sla_days": row.sla_days,
				"jobs": 0, "days": [], "breached": 0, "capacity_kw": 0.0,
			},
		)
		bucket["jobs"] += 1
		bucket["days"].append(flt(row.days_in_stage))
		bucket["breached"] += 1 if row.is_sla_breached else 0
		bucket["capacity_kw"] += flt(row.capacity_kw)

	out = []
	for bucket in buckets.values():
		days = bucket.pop("days")
		bucket["avg_days"] = flt(sum(days) / len(days), 1) if days else 0
		bucket["max_days"] = int(max(days)) if days else 0
		bucket["capacity_kw"] = flt(bucket["capacity_kw"], 2)
		out.append(bucket)
	return sorted(out, key=lambda r: -r["max_days"])
