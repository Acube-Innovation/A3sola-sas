# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A job names its structure contractor and its electrical contractor.

Each running job takes them from what it already shows: the structure contractor from its
Structure work order, the electrical contractor from its material dispatch notice, else its
Installation work order, else its completion-certificate task - the newest of each. A job
with none stays blank. Written directly, so nothing is re-validated.
"""

import frappe


def _newest(doctype, filters):
	rows = frappe.get_all(
		doctype, filters={**filters, "solar_contractor": ["is", "set"], "docstatus": ["<", 2]},
		fields=["solar_contractor"], order_by="creation desc", limit=1,
	)
	return rows[0].solar_contractor if rows else None


def execute():
	frappe.reload_doc("solar_operations", "doctype", "solar_installation")
	for name, structure, electrical in frappe.get_all(
		"Solar Installation", fields=["name", "structure_contractor", "electrical_contractor"], as_list=True
	):
		job = {"solar_installation": name}
		values = {}
		if not structure:
			values["structure_contractor"] = _newest("Installation Work Order", {**job, "work_order_kind": "Structure"})
		if not electrical:
			values["electrical_contractor"] = (
				_newest("Material Dispatch Notice", job)
				or _newest("Installation Work Order", {**job, "work_order_kind": "Installation"})
				or _newest("Installation Task", {**job, "task_code": "CCERT"})
			)
		values = {k: v for k, v in values.items() if v}
		if values:
			frappe.db.set_value("Solar Installation", name, values, update_modified=False)
