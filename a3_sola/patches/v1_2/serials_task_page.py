# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Serials to Electrical Contractor is worked on its own page now (api/serials_task), from
the job's serial register. A draft dispatch notice opened for it and never sent is let go
of: the task no longer points at it, so the page, the board and the completion report all
read the job. Sent notices stay linked, and no notice is deleted."""

import frappe

CODE = "MATL"


def execute():
	rows = frappe.db.sql("""select log.name, log.task_document from `tabInstallation Stage Log` log
		where log.parenttype = 'Solar Installation' and log.stage_code = %s
		and log.task_doctype = 'Material Dispatch Notice' and ifnull(log.task_document, '') != ''""", CODE, as_dict=True)
	for row in rows:
		notice = frappe.db.get_value("Material Dispatch Notice", row.task_document, ["docstatus", "sent_on"], as_dict=True)
		if notice and (notice.docstatus or notice.sent_on):
			continue
		frappe.db.set_value("Installation Stage Log", row.name, "task_document", None, update_modified=False)
