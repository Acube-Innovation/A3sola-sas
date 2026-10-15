# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Structure Material Procurement is due when the advance is received, and buys a list of
materials kept on its task.

Open projects' SPROC rows take the template's due anchor (the advance, same day) and are
re-dated; the material list's table arrives with the doctypes.
"""

import frappe


def execute():
	for doctype in ("installation_task_material", "installation_task", "installation_stage_log"):
		frappe.reload_doc("solar_operations", "doctype", doctype)
	frappe.clear_cache()
	for name in frappe.get_all(
		"Installation Stage Log", filters={"stage_code": "SPROC", "parenttype": "Solar Installation"}, pluck="parent"
	):
		inst = frappe.get_doc("Solar Installation", name)
		if inst.docstatus == 2:
			continue
		for row in inst.stages:
			if row.stage_code == "SPROC":
				row.due_anchor_task, row.due_anchor_days = "ADV", 0
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()
