# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar Portal Registration (NPA) also asks for a pre-installation site photo and the
quotation in the RIM format: the template's checklist takes them, and every running project's
document list takes the rows it does not have yet."""

import frappe

from a3_sola.setup import install_ops

CODE = "NPA"


def execute():
	install_ops.setup()
	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		if not any(r.stage_code == CODE for r in inst.stages):
			continue
		checklist = frappe.db.get_value("Document Checklist Template", {"stage_code": CODE, "company": inst.company}, "name")
		if not checklist:
			continue
		have = {r.document_name for r in inst.documents if r.stage_code == CODE}
		added = False
		for item in frappe.get_doc("Document Checklist Template", checklist).items:
			if item.document_name in have:
				continue
			inst.append("documents", {
				"stage_code": CODE, "document_name": item.document_name, "document_kind": "Expected",
				"is_mandatory": item.is_mandatory, "solar_document_template": item.solar_document_template,
			})
			added = True
		if added:
			inst.flags.ignore_validate_update_after_submit = True
			inst.flags.ignore_permissions = True
			inst.save()
