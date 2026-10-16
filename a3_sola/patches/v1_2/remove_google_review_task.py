# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Google Review is no longer a task: the Customer Review stays, and a Google review is
asked for and recorded on it. The task comes off the shared template and off every project -
its row, its people and its documents still waiting for a file - and its document checklist
goes. Projects are saved directly; their other tasks are not touched."""

import frappe

from a3_sola.api import stages

CODE = "GREV"


def execute():
	for name in frappe.get_all("Installation Stage Template Detail", filters={"stage_code": CODE,
			"parenttype": "Installation Stage Template"}, pluck="parent", distinct=True):
		template = frappe.get_doc("Installation Stage Template", name)
		template.set("stages", [r for r in template.stages if r.stage_code != CODE])
		for index, row in enumerate(template.stages, start=1):
			row.idx = index
		template.flags.ignore_permissions = True
		template.save()
	for name in frappe.get_all("Document Checklist Template", filters={"stage_code": CODE}, pluck="name"):
		frappe.delete_doc("Document Checklist Template", name, ignore_permissions=True, force=True)

	for job in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", job)
		if not any(r.stage_code == CODE for r in inst.stages):
			continue
		inst.set("stages", [r for r in inst.stages if r.stage_code != CODE])
		inst.set("task_assignees", [r for r in inst.get("task_assignees") or [] if r.stage_code != CODE])
		inst.set("documents", [d for d in inst.get("documents") or [] if d.stage_code != CODE or d.attachment])
		for index, row in enumerate(inst.stages, start=1):
			row.idx = index
		stages.recompute(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()
