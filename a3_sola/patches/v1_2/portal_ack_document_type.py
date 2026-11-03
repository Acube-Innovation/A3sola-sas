# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar Acknowledgement as a document type, so the National Portal's acknowledgement is
filed on the Portal Registration task's Attachments card and read into its number and date
(api/portal_ack)."""

import frappe

from a3_sola.setup.custom_fields import DOCUMENT_TYPES


def execute():
	name = frappe.db.get_value("Custom Field", {"dt": "File", "fieldname": "a3s_document_type"}, "name")
	if name:
		frappe.db.set_value("Custom Field", name, "options", DOCUMENT_TYPES)
		frappe.clear_cache(doctype="File")
