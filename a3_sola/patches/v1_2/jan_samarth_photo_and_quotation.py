# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Jan Samarth (DAL) also asks for the pre-installation site photo and the Bank Quotation: a row
for each on the running projects' registers."""

import frappe

CODE = "DAL"
PAPERS = (("Pre-installation site photo", None), ("Bank Quotation", "BANK-QUOTATION"))


def execute():
	for name in frappe.get_all("Installation Stage Log", filters={"parenttype": "Solar Installation",
			"stage_code": CODE, "status": ["!=", "Skipped"]}, pluck="parent", distinct=True):
		inst = frappe.get_doc("Solar Installation", name)
		have = {d.document_name for d in inst.documents if d.stage_code == CODE}
		missing = [(p, code) for p, code in PAPERS if p not in have]
		if not missing:
			continue
		for paper, code in missing:
			template = code and frappe.db.get_value("Solar Document Template",
				{"template_code": code, "company": inst.company}, "name")
			inst.append("documents", {"stage_code": CODE, "document_name": paper, "document_kind": "Expected",
				"is_mandatory": 1, "solar_document_template": template or None})
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_mandatory = True
		inst.save(ignore_permissions=True)
