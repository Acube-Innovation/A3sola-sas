# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Material Procurement (PROC) is worked on its own task - the package's bill of materials as
an editable list with a purchase list to print - not in an ERPNext purchase order.

The template and every open project's PROC row take Installation Task; a row a purchase
order already holds keeps it.
"""

import frappe


def execute():
	for doctype in ("installation_task_material", "installation_task", "installation_stage_log",
	                "installation_stage_template_detail"):
		frappe.reload_doc("solar_operations", "doctype", doctype)
	frappe.clear_cache()
	frappe.db.sql(
		"""update `tabInstallation Stage Template Detail` set task_doctype = 'Installation Task'
		where stage_code = 'PROC' and task_doctype = 'Purchase Order'"""
	)
	frappe.db.sql(
		"""update `tabInstallation Stage Log` set task_doctype = 'Installation Task'
		where stage_code = 'PROC' and task_doctype = 'Purchase Order' and ifnull(task_document, '') = ''"""
	)
