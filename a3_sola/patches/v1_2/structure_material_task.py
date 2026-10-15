# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Structure Material Procurement (SPROC), between Design Freeze and Work Order - Structure.

The shared template takes the task where it belongs; every open project takes it too,
straight after Design Freeze, with its default people and its expected documents. A project
whose structure work order is already done takes it skipped - the material was bought.
"""

import frappe

from a3_sola.api import stages, task_assignees
from a3_sola.setup import install_ops

CODE, AFTER = "SPROC", "DSGN"
#: The task row's own fields, copied from the template row.
ROW_FIELDS = (
	"stage_code", "stage_name", "activity_scope", "owner_type", "responsible_role", "task_doctype",
	"sla_days", "is_mandatory", "due_anchor_task", "due_anchor_days", "default_assignee",
)


def execute():
	for module, doctype in (
		("solar_crm", "solar_package_structure_bom"), ("solar_crm", "solar_package"),
		("solar_operations", "installation_task"), ("solar_operations", "installation_stage_log"),
	):
		frappe.reload_doc(module, "doctype", doctype)
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
		_insert(inst, source, codes.index(AFTER) + 1)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()


def _reorder(template):
	"""The template's rows in task order, so the desk grid reads as the board does."""
	rows = sorted(template.stages, key=lambda r: (r.display_order or 0, r.idx))
	if [r.name for r in rows] == [r.name for r in template.stages]:
		return
	for index, row in enumerate(rows, start=1):
		frappe.db.set_value(row.doctype, row.name, "idx", index, update_modified=False)


def _insert(inst, source, position):
	values = {f: source.get(f) for f in ROW_FIELDS}
	structure_done = any(r.stage_code == "IWOS" and r.status == "Completed" for r in inst.stages)
	values.update({
		"status": "Skipped" if structure_done else "Pending",
		"skip_reason": "Added after the structure was erected" if structure_done else None,
	})
	row = inst.append("stages", values)
	inst.stages.remove(row)
	inst.stages.insert(position, row)
	for index, existing in enumerate(inst.stages, start=1):
		existing.idx = index
	checklist = source.document_checklist_template or frappe.db.get_value(
		"Document Checklist Template", {"stage_code": CODE, "company": inst.company}, "name"
	)
	if checklist:
		stages._append_checklist(inst, CODE, checklist)
	stages.plan_dates(inst)
	task_assignees.apply_defaults(inst)
