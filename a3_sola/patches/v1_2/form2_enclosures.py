# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 2 (FRM2) also asks for the solar panel test certificate and the panel and inverter data
sheets: a row for each on the running projects' registers."""

import frappe

CODE = "FRM2"
PAPERS = ("Solar Panel Test Certificate", "Solar Panel Data Sheet", "Inverter Data Sheet")


def execute():
	for name in frappe.get_all("Installation Stage Log", filters={"parenttype": "Solar Installation",
			"stage_code": CODE, "status": ["!=", "Skipped"]}, pluck="parent", distinct=True):
		inst = frappe.get_doc("Solar Installation", name)
		have = {d.document_name for d in inst.documents if d.stage_code == CODE}
		missing = [p for p in PAPERS if p not in have]
		if not missing:
			continue
		for paper in missing:
			inst.append("documents", {"stage_code": CODE, "document_name": paper, "document_kind": "Expected",
				"is_mandatory": 1})
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_mandatory = True
		inst.save(ignore_permissions=True)
