# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Table fields left behind by an app no longer installed - India Compliance's "Company Print
Options" on Company, its taxes table on Stock Entry and Subcontracting, HRMS's approvers on
Department - stop the record saving: on every save Frappe builds a row of each table, and the
row's DocType's code went with its app ("Module GST India not found").

Each such Custom Field is removed, only while its table holds no rows, so nothing entered is
lost. Link fields to those apps' DocTypes are left: they do not stop a save."""

import frappe


def orphan_doctypes():
	"""DocTypes whose module belongs to an app not installed on the site."""
	installed = set(frappe.get_installed_apps())
	modules = [m.name for m in frappe.get_all("Module Def", fields=["name", "app_name"]) if m.app_name not in installed]
	if not modules:
		return set()
	return set(frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name"))


def execute():
	orphans = orphan_doctypes()
	if not orphans:
		return
	for cf in frappe.get_all("Custom Field", filters={"fieldtype": ["in", ["Table", "Table MultiSelect"]],
			"options": ["in", list(orphans)]}, fields=["name", "dt", "fieldname", "options"]):
		if frappe.db.table_exists(cf.options) and frappe.db.count(cf.options, {"parenttype": cf.dt, "parentfield": cf.fieldname}):
			continue
		frappe.delete_doc("Custom Field", cf.name, ignore_permissions=True, force=True)
		frappe.clear_cache(doctype=cf.dt)
