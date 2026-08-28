# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Document Pack Status.

The documentation officer's daily worklist, and the one report that says whether a job is
actually ready for its next external step."""

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
		{"label": _("Installation"), "fieldname": "name", "fieldtype": "Link", "options": "Solar Installation", "width": 150},
		{"label": _("Consumer"), "fieldname": "consumer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Current Stage"), "fieldname": "current_stage", "fieldtype": "Data", "width": 170},
		{"label": _("Due"), "fieldname": "due", "fieldtype": "Int", "width": 70},
		{"label": _("Attached"), "fieldname": "attached", "fieldtype": "Int", "width": 90},
		{"label": _("Verified"), "fieldname": "verified", "fieldtype": "Int", "width": 90},
		{"label": _("Missing"), "fieldname": "missing_count", "fieldtype": "Int", "width": 90},
		{"label": _("Stale"), "fieldname": "stale_document_count", "fieldtype": "Int", "width": 80},
		{"label": _("Outstanding Documents"), "fieldname": "missing", "fieldtype": "Data", "width": 420},
	]


def get_data(filters):
	installations = frappe.get_list(
		"Solar Installation",
		filters={"company": filters.company, "docstatus": 1,
		         "status": ["not in", ["Closed", "Cancelled"]]},
		fields=["name", "consumer_name", "current_stage", "stale_document_count"],
		limit_page_length=0,
	)
	out = []
	for row in installations:
		doc = frappe.get_doc("Solar Installation", row.name)
		current_code = None
		for stage in doc.stages:
			if stage.status in ("In Progress", "Blocked"):
				current_code = stage.stage_code
				break
		due = [d for d in doc.documents if d.is_mandatory and (not current_code or d.stage_code == current_code)]
		missing = [d.document_name for d in due if not d.attachment or not d.is_verified]
		row["due"] = len(due)
		row["attached"] = len([d for d in due if d.attachment])
		row["verified"] = len([d for d in due if d.is_verified])
		row["missing_count"] = len(missing)
		row["missing"] = ", ".join(missing)
		out.append(row)
	return sorted(out, key=lambda r: -r["missing_count"])
