# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer made from its lead holds what the lead holds: each file attached to the lead -
the KSEB bill, the Aadhaar, any other - attached to the customer too, with the type it was filed
as and, for a KYC paper, its KYC row; and the lead's gender where the customer has none. Customers
made before this get them now; new ones are made with them (Solar Consumer.after_insert)."""

import frappe

from a3_sola.api import kyc, portal_attachments

CONSUMER = "Solar Consumer"


def execute():
	kinds = portal_attachments._kyc_types()
	for row in frappe.get_all(CONSUMER, filters={"lead": ["is", "set"]}, fields=["name", "lead", "gender"]):
		if not frappe.db.exists("Lead", row.lead):
			continue
		if not row.gender:
			gender = frappe.db.get_value("Lead", row.lead, "gender")
			if gender:
				frappe.db.set_value(CONSUMER, row.name, "gender", gender, update_modified=False)
		try:
			copied = portal_attachments.copy_lead_files(row.name, row.lead)
			for f in copied:
				if f.a3s_document_type in kinds:
					portal_attachments._sync_kyc(row.name, f.file_url, f.a3s_document_type)
			if copied:
				kyc.refresh(row.name)
		except Exception:
			frappe.log_error(title=f"Lead files not copied to customer {row.name}")
