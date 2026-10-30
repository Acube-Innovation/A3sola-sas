# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The company is Renewcore Innovations LLP: the Company first set up as "Acube Innovations"
takes its real name, and its abbreviation AI becomes RIL, so its accounts, cost centers,
warehouses, departments and tax templates are named "... - RIL".

Frappe's rename carries every link to the renamed records - those of doctypes whose app is no
longer installed (HRMS's, left behind) are skipped, as their code cannot be loaded. A site
without that company, or already renamed, is left as it is."""

from contextlib import contextmanager

import frappe
from frappe.model import rename_doc as renamer

OLD, NEW = "Acube Innovations", "Renewcore Innovations LLP"
OLD_ABBR, NEW_ABBR = "AI", "RIL"


def execute():
	if not frappe.db.exists("Company", OLD) or frappe.db.exists("Company", NEW):
		return
	with installed_links_only():
		rename()


def rename():
	frappe.rename_doc("Company", OLD, NEW, force=True)
	if frappe.db.get_value("Company", NEW, "abbr") != OLD_ABBR:
		frappe.db.commit()
		return
	frappe.db.set_value("Company", NEW, "abbr", NEW_ABBR)
	old, new = f" - {OLD_ABBR}", f" - {NEW_ABBR}"
	renamed = 0
	for doctype in company_named_doctypes():
		for name in frappe.get_all(doctype, filters={"company": NEW, "name": ["like", f"%{old}"]}, pluck="name"):
			target = name[: -len(old)] + new
			if not frappe.db.exists(doctype, target):
				frappe.rename_doc(doctype, name, target, force=True)
				renamed += 1
	frappe.db.commit()
	print(f"Company renamed to {NEW}; {renamed} records now end in '{new}'.")


@contextmanager
def installed_links_only():
	"""Rename only through the link fields of installed apps' doctypes."""
	installed = set(frappe.get_all("Module Def", filters={"app_name": ["in", frappe.get_installed_apps()]}, pluck="name"))
	modules = dict(frappe.get_all("DocType", fields=["name", "module"], as_list=True))
	original = renamer.get_link_fields
	renamer.get_link_fields = lambda doctype: [f for f in original(doctype) if modules.get(f["parent"]) in installed]
	try:
		yield
	finally:
		renamer.get_link_fields = original


def company_named_doctypes():
	"""Doctypes whose records belong to a company and carry its abbreviation in their name."""
	out = []
	for doctype in frappe.get_all("DocField", filters={"fieldname": "company", "fieldtype": "Link", "options": "Company"},
			pluck="parent", distinct=True):
		if frappe.db.get_value("DocType", doctype, "module") not in frappe.get_all(
				"Module Def", filters={"app_name": ["in", frappe.get_installed_apps()]}, pluck="name"):
			continue
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle or meta.is_virtual or not frappe.db.table_exists(doctype):
			continue
		if frappe.db.exists(doctype, {"name": ["like", f"% - {OLD_ABBR}"]}):
			out.append(doctype)
	return out
