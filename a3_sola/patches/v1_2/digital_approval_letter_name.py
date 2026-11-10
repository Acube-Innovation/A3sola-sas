# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Jan Samarth's letter is the "Digital Approval Letter" on the project's documents, as on its
task's Attachments card: the register rows, the checklist and the files filed under the old name."""

import frappe

CODE = "DAL"
OLD, NEW = "Jan Samarth approval letter", "Digital Approval Letter"


def execute():
	frappe.db.sql("""update `tabInstallation Document` set document_name=%s
		where stage_code=%s and document_name=%s and parenttype='Solar Installation'""", (NEW, CODE, OLD))
	frappe.db.sql("""update `tabDocument Checklist Template Item` set document_name=%s where document_name=%s""", (NEW, OLD))
	frappe.db.sql("""update `tabFile` set a3s_document_type=%s where a3s_document_type=%s""", (NEW, OLD))
