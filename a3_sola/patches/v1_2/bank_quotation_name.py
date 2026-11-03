# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The quotation the bank gets, in the RIM format, is the "Bank Quotation" on every task's
checklist and on the running projects' registers."""

import frappe

OLD, NEW = "Quotation (RIM format)", "Bank Quotation"


def execute():
	frappe.db.sql("update `tabInstallation Document` set document_name = %s where document_name = %s", (NEW, OLD))
	frappe.db.sql("update `tabFile` set a3s_document_type = %s where a3s_document_type = %s", (NEW, OLD))
