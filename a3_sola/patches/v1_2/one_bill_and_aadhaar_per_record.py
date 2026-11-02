# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A lead's or customer's KSEB bill and Aadhaar sides, one of each: where a record has several
of one (a bill read twice), the newest is kept and the others removed, as an upload now does
(portal_attachments.supersede)."""

import frappe

from a3_sola.api.portal_attachments import SINGLE_TYPES, supersede


def execute():
	groups = frappe.db.sql("""select attached_to_doctype, attached_to_name, a3s_document_type
		from `tabFile` where a3s_document_type in %(types)s and is_folder = 0 and attached_to_name is not null
		group by attached_to_doctype, attached_to_name, a3s_document_type having count(*) > 1""",
		{"types": SINGLE_TYPES}, as_dict=True)
	for g in groups:
		newest = frappe.get_all("File", filters={"attached_to_doctype": g.attached_to_doctype,
			"attached_to_name": g.attached_to_name, "a3s_document_type": g.a3s_document_type, "is_folder": 0},
			fields=["file_url"], order_by="creation desc", limit=1)
		if newest and frappe.db.exists(g.attached_to_doctype, g.attached_to_name):
			supersede(g.attached_to_doctype, g.attached_to_name, g.a3s_document_type, newest[0].file_url)
	frappe.db.commit()
