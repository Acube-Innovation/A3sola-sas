# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The work orders - structure, then installation - follow Material Dispatch: the material
is on site before the crews are.

The shared template takes the new order (its rows' display order is the seed's), and every
running project's tasks are put in the template's order. Nothing done or started changes
status; the planned dates are laid end to end again in the new order.
"""

import frappe

from a3_sola.api import stages
from a3_sola.patches.v1_2.structure_material_task import _reorder
from a3_sola.setup import install_ops


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_log")
	install_ops.seed_stage_templates()
	name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if not name:
		return
	template = frappe.get_doc("Installation Stage Template", name)
	_reorder(template)
	order = {r.stage_code: r.display_order or r.idx for r in template.stages}

	for job in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", job)
		# A task the template does not know keeps its place behind the ones it does.
		rows = sorted(inst.stages, key=lambda r: (order.get(r.stage_code, 10**6), r.idx))
		if [r.name for r in rows] == [r.name for r in inst.stages]:
			continue
		inst.set("stages", rows)
		for index, row in enumerate(inst.stages, start=1):
			row.idx = index
		stages.plan_dates(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()
