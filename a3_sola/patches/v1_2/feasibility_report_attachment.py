# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 1's feasibility report moves from the task's form to its Attachments card: a report
already in the field is filed there, as Feasibility Report, and on the project's register."""

import frappe


def execute():
	from a3_sola.api import task_files

	for task in frappe.get_all("Installation Task", filters={"feasibility_report": ["is", "set"]},
			fields=["name", "feasibility_report"]):
		url = task.feasibility_report
		files = frappe.get_all("File", filters={"attached_to_doctype": "Installation Task", "attached_to_name": task.name,
			"file_url": url}, fields=["name", "a3s_document_type"])
		if files:
			for f in files:
				if not f.a3s_document_type:
					frappe.db.set_value("File", f.name, "a3s_document_type", "Feasibility Report", update_modified=False)
		else:
			source = frappe.db.get_value("File", {"file_url": url}, ["file_name", "is_private"], as_dict=True) or {}
			frappe.get_doc({"doctype": "File", "file_url": url, "file_name": source.get("file_name") or "Feasibility Report",
				"is_private": source.get("is_private", 1), "attached_to_doctype": "Installation Task",
				"attached_to_name": task.name, "a3s_document_type": "Feasibility Report"}).insert(ignore_permissions=True)
		try:
			task_files.on_attached("Installation Task", task.name, "Feasibility Report", url)
		except Exception:
			frappe.log_error(title="Feasibility report not on the register: " + task.name)
