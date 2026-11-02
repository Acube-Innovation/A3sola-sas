# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Supplier Invoice task after Material Dispatch: the supplier's bill for a job's material
read from its PDF into an ERPNext Purchase Invoice on the job (api/supplier_bill). Purchase
Invoice gets the job's link and the mark of a material bill; every open job takes the task,
pending, after its dispatch."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from a3_sola.api import stages, task_assignees
from a3_sola.setup import install_ops
from a3_sola.setup.custom_fields_ops import CUSTOM_FIELDS

CODE, AFTER = "SUPINV", "DISP"
ROW_FIELDS = (
	"stage_code", "stage_name", "activity_scope", "owner_type", "responsible_role", "task_doctype",
	"sla_days", "is_mandatory", "due_anchor_task", "due_anchor_days", "default_assignee",
)


def execute():
	create_custom_fields({"Purchase Invoice": CUSTOM_FIELDS["Purchase Invoice"]}, update=True)
	frappe.clear_cache()
	install_ops.setup()

	name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if not name:
		return
	template = frappe.get_doc("Installation Stage Template", name)
	rows = sorted(template.stages, key=lambda r: (r.display_order or 0, r.idx))
	for index, r in enumerate(rows, start=1):
		frappe.db.set_value(r.doctype, r.name, "idx", index, update_modified=False)
	source = next((r for r in template.stages if r.stage_code == CODE), None)
	if not source:
		return

	for job in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", job)
		codes = [r.stage_code for r in inst.stages]
		if CODE in codes:
			continue
		row = inst.append("stages", {**{f: source.get(f) for f in ROW_FIELDS}, "status": "Pending"})
		inst.stages.remove(row)
		inst.stages.insert(codes.index(AFTER) + 1 if AFTER in codes else len(inst.stages), row)
		for index, existing in enumerate(inst.stages, start=1):
			existing.idx = index
		stages.plan_dates(inst)
		task_assignees.apply_defaults(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.flags.ignore_mandatory = True  # a job short of a field it was submitted without
		inst.save()
