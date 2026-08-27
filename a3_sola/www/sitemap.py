# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""sitemap.xml, generated from what is actually published.

Regenerated on every request rather than cached to disk: unpublishing a feature has to
take it out of the sitemap immediately, and the page count here is small enough that
building it per request costs nothing.
"""

import frappe

from a3_sola.api import platform

no_cache = 1

#: Static marketing routes. The signup funnel is deliberately absent - see robots.py.
STATIC_ROUTES = (
	("", 1.0, "weekly"),
	("features", 0.9, "weekly"),
	("solutions", 0.9, "weekly"),
	("pricing", 0.9, "weekly"),
	("legal/privacy", 0.3, "yearly"),
	("legal/terms", 0.3, "yearly"),
	("legal/refund-policy", 0.3, "yearly"),
)


def get_context(context):
	context.no_cache = 1
	entries = [
		{
			"url": frappe.utils.get_url(route),
			"priority": priority,
			"changefreq": frequency,
			"lastmod": None,
		}
		for route, priority, frequency in STATIC_ROUTES
	]

	for doctype in ("Platform Feature", "Platform Solution"):
		for row in frappe.get_all(
			doctype, filters={"is_published": 1}, fields=["route", "modified"]
		):
			entries.append(
				{
					"url": frappe.utils.get_url(row.route),
					"priority": 0.7,
					"changefreq": "monthly",
					"lastmod": frappe.utils.get_datetime(row.modified).strftime("%Y-%m-%d"),
				}
			)

	context.entries = entries
	return context
