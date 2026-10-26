# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""India Compliance, once installed and then removed, leaves custom fields whose show and
mandatory rules read its `gst_settings` - a browser global only that app defines. Without it
every such rule fails and the form says "Invalid depends_on expression" (Item, Sales Invoice,
Address...). Each `gst_settings.x` reads `(window.gst_settings || {}).x` instead: off without
the app, as its settings default to, and unchanged with it.
"""

import re

import frappe

GUARD = "(window.gst_settings || {})."
BARE = re.compile(r"(?<![\w.])gst_settings\.")
RULES = ("depends_on", "mandatory_depends_on", "read_only_depends_on")


def guard(expression):
	return BARE.sub(GUARD, expression)


def execute():
	if "india_compliance" in frappe.get_installed_apps():
		return
	for field in RULES:
		for row in frappe.get_all("Custom Field", filters={field: ["like", "%gst_settings.%"]}, fields=["name", field]):
			frappe.db.set_value("Custom Field", row.name, field, guard(row[field]), update_modified=False)
	for row in frappe.get_all("Property Setter", filters={"property": ["in", RULES], "value": ["like", "%gst_settings.%"]},
			fields=["name", "value"]):
		frappe.db.set_value("Property Setter", row.name, "value", guard(row.value), update_modified=False)
	frappe.clear_cache()
