# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Each procurement task says how its material reaches the site. The tasks already on file
ship from the vendor's door - what their purchase list has always printed - and show who is
billed and where it goes. Material Dispatch is left as it is until a task is next saved.
Written directly, so nothing is re-validated."""

import frappe

from a3_sola.api import material_delivery


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_task")
	for name in frappe.get_all("Installation Task", filters={"task_code": ["in", list(material_delivery.PROCUREMENT)]},
			pluck="name"):
		task = frappe.get_doc("Installation Task", name)
		task.delivery_method = task.delivery_method or material_delivery.VENDOR
		if not frappe.db.exists("Solar Installation", task.solar_installation):
			continue
		bill_to, ship_to = material_delivery.blocks(task)
		frappe.db.set_value("Installation Task", name, {"delivery_method": task.delivery_method,
			"bill_to": bill_to, "ship_to": ship_to}, update_modified=False)
