# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Digital Approval Letter as a document type, so the Jan Samarth task's letter is filed on its
Attachments card as every other task's documents are (installation_task.approval_letters)."""

import frappe

from a3_sola.setup.custom_fields import DOCUMENT_TYPES


def execute():
	name = frappe.db.get_value("Custom Field", {"dt": "File", "fieldname": "a3s_document_type"}, "name")
	if name:
		frappe.db.set_value("Custom Field", name, "options", DOCUMENT_TYPES)
		frappe.clear_cache(doctype="File")
