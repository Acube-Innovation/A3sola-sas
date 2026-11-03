# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task's documents are one list (api/task_files): a file's document type becomes free text -
a task's own documents are types too - and every task's files already filed on its record or
on the project's register are filed in the other place as well."""

import frappe


def execute():
	name = frappe.db.get_value("Custom Field", {"dt": "File", "fieldname": "a3s_document_type"}, "name")
	if name:
		frappe.db.set_value("Custom Field", name, {"fieldtype": "Data", "options": None})
		frappe.clear_cache(doctype="File")
	from a3_sola.api import task_files

	for inst_name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", inst_name)
		for row in inst.stages:
			if row.task_doctype and row.task_document:
				try:
					task_files.sync_task(inst, row.stage_code)
					inst.reload()
				except Exception:
					frappe.log_error(title=f"Task documents sync: {inst_name} {row.stage_code}")
