# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The bank's loan pack: a Digital Approval Letter task (from Jan Samarth) after portal
registration on financed jobs, a Building Tax Receipt type for the consumer's papers, and the
RIM quotation template.

Open projects take the task after NPA - pending when financed, skipped when not.
"""

import frappe

from a3_sola.api import stages, task_assignees
from a3_sola.setup import install_ops
from a3_sola.setup.custom_fields import DOCUMENT_TYPES

CODE, AFTER = "DAL", "NPA"
ROW_FIELDS = (
	"stage_code", "stage_name", "activity_scope", "owner_type", "responsible_role", "task_doctype",
	"sla_days", "is_mandatory", "due_anchor_task", "due_anchor_days", "default_assignee",
)


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_task")
	name = frappe.db.get_value("Custom Field", {"dt": "File", "fieldname": "a3s_document_type"}, "name")
	if name:
		frappe.db.set_value("Custom Field", name, "options", DOCUMENT_TYPES)
	frappe.clear_cache()
	install_ops.setup()

	template = frappe.get_doc("Installation Stage Template", frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name"))
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
		values = {f: source.get(f) for f in ROW_FIELDS}
		values.update({"status": "Pending" if inst.is_financed else "Skipped",
			"skip_reason": None if inst.is_financed else "Self-funded sale"})
		row = inst.append("stages", values)
		inst.stages.remove(row)
		inst.stages.insert(codes.index(AFTER) + 1 if AFTER in codes else 0, row)
		for index, existing in enumerate(inst.stages, start=1):
			existing.idx = index
		stages.plan_dates(inst)
		task_assignees.apply_defaults(inst)
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.save()
