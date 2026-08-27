# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Content Performance.

What is on the site, what is stale and what has no copy behind it. Page-view counts are
deliberately absent: this app has no server-side analytics store, and inventing numbers
here would be worse than leaving the column out.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Type"), "fieldname": "doctype_label", "fieldtype": "Data", "width": 140},
		{"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 260},
		{"label": _("Route"), "fieldname": "route", "fieldtype": "Data", "width": 240},
		{"label": _("Published"), "fieldname": "is_published", "fieldtype": "Check", "width": 100},
		{"label": _("On Homepage"), "fieldname": "show_on_homepage", "fieldtype": "Check", "width": 130},
		{"label": _("Has Detail Copy"), "fieldname": "has_detail", "fieldtype": "Check", "width": 140},
		{"label": _("Has Meta Description"), "fieldname": "has_meta", "fieldtype": "Check", "width": 180},
		{"label": _("Last Edited"), "fieldname": "modified", "fieldtype": "Date", "width": 120},
		{"label": _("Days Since Edit"), "fieldname": "days_stale", "fieldtype": "Int", "width": 150},
	]


def get_data(filters):
	out = []
	for doctype, title_field in (
		("Platform Feature", "feature_name"),
		("Platform Solution", "solution_name"),
	):
		for row in frappe.get_all(
			doctype,
			fields=[
				f"{title_field} as title", "route", "is_published", "show_on_homepage",
				"body_content", "meta_description", "modified",
			],
			limit_page_length=0,
		):
			out.append(
				{
					"doctype_label": doctype.replace("Platform ", ""),
					"title": row.title,
					"route": row.route,
					"is_published": row.is_published,
					"show_on_homepage": row.show_on_homepage,
					"has_detail": 1 if (row.body_content or "").strip() else 0,
					"has_meta": 1 if (row.meta_description or "").strip() else 0,
					"modified": getdate(row.modified),
					"days_stale": date_diff(today(), getdate(row.modified)),
				}
			)

	for row in frappe.get_all(
		"Platform Legal Page",
		fields=["title", "page_key", "is_published", "reviewed_by_lawyer", "modified"],
		limit_page_length=0,
	):
		out.append(
			{
				"doctype_label": "Legal",
				"title": row.title,
				"route": f"legal/{row.page_key}",
				"is_published": row.is_published,
				"show_on_homepage": 0,
				# For a legal page, "has detail copy" means a lawyer has actually seen it.
				"has_detail": row.reviewed_by_lawyer,
				"has_meta": 1,
				"modified": getdate(row.modified),
				"days_stale": date_diff(today(), getdate(row.modified)),
			}
		)

	out.sort(key=lambda r: r["days_stale"], reverse=True)
	return out
