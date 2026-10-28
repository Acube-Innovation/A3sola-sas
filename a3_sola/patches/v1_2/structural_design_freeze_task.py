# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Design Freeze is now Solar Design Freeze (DSGN: the material BOM, the single line diagram),
followed by Structural Design Freeze (SDSGN: the structure BOM, the structure drawing).

The shared template takes the new task and the new name; every open project takes the task
straight after DSGN, as far along as DSGN is - the two were frozen together until now - with
its default people and its expected documents. A structure drawing filed under DSGN moves to it.
"""

import frappe

from a3_sola.api import stages, task_assignees
from a3_sola.patches.v1_2.structure_material_task import _reorder
from a3_sola.setup import install_ops

CODE, AFTER = "SDSGN", "DSGN"
DRAWING = "structure drawing"
#: The task row's own fields, copied from the template row.
ROW_FIELDS = (
	"stage_code", "stage_name", "activity_scope", "owner_type", "responsible_role", "task_doctype",
	"sla_days", "is_mandatory", "due_anchor_task", "due_anchor_days", "default_assignee",
)
#: What the new row takes from DSGN on a running job.
PROGRESS_FIELDS = ("status", "skip_reason", "actual_start_date", "actual_completion_date", "completed_by")


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_task")
	frappe.clear_cache()
	install_ops.setup()

	template_name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if not template_name:
		return
	template = frappe.get_doc("Installation Stage Template", template_name)
	_reorder(template)
	source = next((r for r in template.stages if r.stage_code == CODE), None)
	if not source:
		return

	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		codes = [r.stage_code for r in inst.stages]
		if CODE in codes or AFTER not in codes:
			continue
		design = inst.stages[codes.index(AFTER)]
		values = {f: source.get(f) for f in ROW_FIELDS}
		values.update({f: design.get(f) for f in PROGRESS_FIELDS if design.get(f)})
		values.setdefault("status", "Pending")
		row = inst.append("stages", values)
		inst.stages.remove(row)
		inst.stages.insert(codes.index(AFTER) + 1, row)
		for index, existing in enumerate(inst.stages, start=1):
			existing.idx = index
		moved = False
		for d in inst.documents:
			if d.stage_code == AFTER and (d.document_name or "").strip().lower() == DRAWING:
				d.stage_code, moved = CODE, True
		checklist = source.document_checklist_template or frappe.db.get_value(
			"Document Checklist Template", {"stage_code": CODE, "company": inst.company}, "name"
		)
		if checklist and not moved:
			stages._append_checklist(inst, CODE, checklist)
		stages.plan_dates(inst)
		task_assignees.apply_defaults(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.flags.ignore_links = True
		inst.save()
