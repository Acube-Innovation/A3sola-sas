# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Accept Customer: the customer accepted on the PM Surya Ghar portal for a loan, with the Net
Metering Agreement (NET.pdf) generated in the task. Second in the PM Surya Ghar column, after
the portal registration, on financed jobs only.

Every company gets the agreement's template; open projects take the task after NPA - pending
when financed, skipped when not.
"""

import frappe

from a3_sola.api import stages, task_assignees
from a3_sola.setup import install_ops

CODE, AFTER = "ACPT", "NPA"
ROW_FIELDS = (
	"stage_code", "stage_name", "activity_scope", "owner_type", "responsible_role", "task_doctype",
	"sla_days", "is_mandatory", "applicability", "due_anchor_task", "due_anchor_days", "default_assignee",
)


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_task")
	frappe.clear_cache()
	install_ops.setup()
	for company in frappe.get_all("Company", pluck="name"):
		install_ops.seed_document_templates(company)

	name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if not name:
		return
	template = frappe.get_doc("Installation Stage Template", name)
	rows = sorted(template.stages, key=lambda r: (r.display_order or 0, r.idx))
	for index, r in enumerate(rows, start=1):
		frappe.db.set_value(r.doctype, r.name, "idx", index, update_modified=False)
	frappe.clear_document_cache("Installation Stage Template", name)
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
