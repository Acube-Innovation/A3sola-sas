# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer pays in the phases of the payment terms: Advance, Payment after Installation
(the Balance Payment, renamed and moved after the completion certificate) and Payment after
Commissioning (new, after Commissioning) - each on its own payment page, with anything unpaid
before (api/payment_tasks).

The shared template takes the new task and names; every running project gets Payment after
Commissioning - skipped where its terms have no third payment - and its tasks are put in the
template's order. Nothing done or started changes status."""

import frappe

from a3_sola.api import payment_tasks, stages, task_assignees
from a3_sola.patches.v1_2 import work_orders_after_dispatch
from a3_sola.patches.v1_2.structure_material_task import ROW_FIELDS
from a3_sola.setup import install_ops

CODE = "PCOM"


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_log")
	frappe.clear_cache()
	install_ops.setup()  # the template's new row and names, and the new task's checklist
	template_name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if not template_name:
		return
	template = frappe.get_doc("Installation Stage Template", template_name)
	source = next((r for r in template.stages if r.stage_code == CODE), None)
	names = {r.stage_code: r.stage_name for r in template.stages}

	for job in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", job)
		for row in inst.stages:
			if row.stage_code in ("BAL", CODE) and names.get(row.stage_code) and row.stage_name != names[row.stage_code]:
				row.stage_name = names[row.stage_code]
		if source and not any(r.stage_code == CODE for r in inst.stages):
			inst.append("stages", {**{f: source.get(f) for f in ROW_FIELDS}, "status": "Pending"})
			checklist = source.document_checklist_template or frappe.db.get_value(
				"Document Checklist Template", {"stage_code": CODE, "company": inst.company}, "name")
			if checklist:
				stages._append_checklist(inst, CODE, checklist)
			task_assignees.apply_defaults(inst)
		payment_tasks.apply_phases(inst)
		stages.recompute(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()

	# Every task in the template's order, the new one after Commissioning.
	work_orders_after_dispatch.execute()
