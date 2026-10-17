# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 2 & 3 Submission is two tasks: Form 2 Submission (FRM2), within thirty days of the
Form 1 fee and with no agreement, then Form 2 Payment, then Form 3 Submission (KFORMS) - the
completion papers with the executed agreement.

The shared template takes FRM2 and the new order; the KSEB pack is renamed "KSEB Form 3";
every running project takes FRM2 in its place, with the Form 2 rows of its document list.
A project whose Form 2 & 3 was already submitted takes Form 2 skipped - it went with it - and
one that skipped Form 2 & 3 skips Form 2 too, for the same reason.
"""

import frappe

from a3_sola.api import stages, task_assignees
from a3_sola.patches.v1_2.structure_material_task import ROW_FIELDS, _reorder
from a3_sola.setup import install_ops

CODE, COMBINED = "FRM2", "KFORMS"
#: The job's document rows that are Form 2's now.
FORM2_DOCUMENTS = ("Annexure / Form 2", "AE acknowledged Form 2")
FORM2_TEMPLATE = "KSEB-FORM-2"


def execute():
	for module, doctype in (
		("solar_operations", "document_pack"), ("solar_crm", "discom_section"),
		("solar_operations", "installation_stage_log"), ("solar_operations", "installation_document"),
	):
		frappe.reload_doc(module, "doctype", doctype)
	frappe.db.sql("""update `tabDocument Pack` set pack_type = 'KSEB Form 3' where pack_type = 'KSEB Submission'""")
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
	order = {r.stage_code: r.display_order or r.idx for r in template.stages}

	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		codes = [r.stage_code for r in inst.stages]
		if CODE in codes or COMBINED not in codes:
			continue
		split(inst, source, order)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()
	frappe.clear_document_cache("Installation Stage Template", template_name)


def split(inst, source, order):
	"""FRM2 on one job: added, given its documents, and the tasks put in the template's order."""
	combined = next(r for r in inst.stages if r.stage_code == COMBINED)
	values = {f: source.get(f) for f in ROW_FIELDS}
	if combined.status == "Completed":
		values.update({"status": "Skipped", "skip_reason": "Done with Form 2 & 3 before the split"})
	elif combined.status == "Skipped":
		# Form 2 & 3 was not needed on this job: nor is Form 2, for the same reason.
		values.update({"status": "Skipped", "skip_reason": combined.skip_reason})
	else:
		values["status"] = "Pending"
	inst.append("stages", values)

	moved = False
	for row in inst.documents or []:
		if row.stage_code == COMBINED and (row.document_name in FORM2_DOCUMENTS
				or row.solar_document_template == FORM2_TEMPLATE):
			row.stage_code = CODE
			moved = True
	checklist = source.document_checklist_template
	if not moved and checklist:
		stages._append_checklist(inst, CODE, checklist)

	rows = sorted(inst.stages, key=lambda r: (order.get(r.stage_code, 10**6), r.idx))
	inst.set("stages", rows)
	for index, row in enumerate(inst.stages, start=1):
		row.idx = index
	stages.plan_dates(inst)
	task_assignees.apply_defaults(inst)
