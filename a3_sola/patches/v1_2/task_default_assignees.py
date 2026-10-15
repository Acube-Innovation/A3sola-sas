# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every task has a default assignee, and a task any number of people.

The shared template's rows take their seeded Default Assignee where they have none; each
open job takes a Project Engineer and Sales Co-ordinator where one person holds the role,
and its tasks with nobody on them go to their default people.
"""

import frappe

from a3_sola.api import task_assignees
from a3_sola.setup import install_ops


def execute():
	for doctype in ("installation_stage_template_detail", "installation_stage_log", "installation_task_assignee",
	                "solar_installation"):
		frappe.reload_doc("solar_operations", "doctype", doctype)
	# The rows are read by field name below; a cached meta from before the reload drops them.
	frappe.clear_cache()
	if frappe.db.exists("Installation Stage Template", {"is_shared": 1}):
		install_ops.seed_stage_templates()
	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		task_assignees.prefill_people(inst)
		task_assignees.apply_defaults(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		try:
			inst.save()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: default assignees for {name}")
