# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar registration (NPA) also expects the feasibility report, the e-token and the net
meter agreement the portal gives back: a row for each on the running projects' registers."""

import frappe

CODE = "NPA"
PAPERS = ("Feasibility Report", "E-Token", "Net Meter Agreement")


def execute():
	installations = frappe.get_all("Installation Stage Log", filters={"parenttype": "Solar Installation",
		"stage_code": CODE, "status": ["!=", "Skipped"]}, pluck="parent", distinct=True)
	for name in installations:
		inst = frappe.get_doc("Solar Installation", name)
		have = {d.document_name for d in inst.documents if d.stage_code == CODE}
		added = False
		for paper in PAPERS:
			if paper not in have:
				inst.append("documents", {"stage_code": CODE, "document_name": paper,
					"document_kind": "Expected", "is_mandatory": 0})
				added = True
		if added:
			# Files of these types already on the task's record fill their new rows.
			for f in frappe.get_all("File", filters={"attached_to_doctype": "Portal Application",
					"a3s_document_type": ["in", PAPERS], "attached_to_name": ["in", [r.task_document for r in inst.stages
					if r.stage_code == CODE and r.task_doctype == "Portal Application" and r.task_document] or [""]]},
					fields=["file_url", "a3s_document_type"]):
				row = next((d for d in inst.documents if d.stage_code == CODE and d.document_name == f.a3s_document_type
					and not d.attachment), None)
				if row:
					row.update({"document_kind": "Uploaded", "attachment": f.file_url})
			inst.flags.ignore_validate_update_after_submit = True
			inst.flags.ignore_mandatory = True
			inst.flags.ignore_permissions = True
			inst.save(ignore_permissions=True)
