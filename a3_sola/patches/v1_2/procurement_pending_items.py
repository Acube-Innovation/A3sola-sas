# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Pending items are a table of their own now: a Pending Qty already entered on a
procurement task's list moves off the list into its Pending Items, as a save does."""

import frappe

from a3_sola.api.purchase_list import move_to_pending


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_task_pending_item")
	frappe.reload_doc("solar_operations", "doctype", "installation_task")
	tasks = frappe.db.sql_list("""select distinct parent from `tabInstallation Task Material`
		where parenttype = 'Installation Task' and pending_qty > 0""")
	for name in tasks:
		doc = frappe.get_doc("Installation Task", name)
		before = {row.name: row.qty for row in doc.get("materials") + doc.get("structure_materials")}
		move_to_pending(doc)
		# Only the moved quantities are written: the task's other rules are not re-run here.
		for row in doc.get("materials") + doc.get("structure_materials"):
			if row.name in before:
				frappe.db.set_value("Installation Task Material", row.name, {"qty": row.qty, "pending_qty": 0},
					update_modified=False)
		for row in doc.get("pending_items"):
			if row.is_new() or not frappe.db.exists("Installation Task Pending Item", row.name):
				row.db_insert()
