# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Task rows carry their activity scope and a planned start and end from the job's start date.

Every job starts its plan on its order date. Rows are written directly, so submitted jobs
are planned without re-running their submission checks.
"""

import frappe

from a3_sola.api import stages


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_log")
	frappe.reload_doc("solar_operations", "doctype", "solar_installation")
	for name in frappe.get_all("Solar Installation", pluck="name"):
		doc = frappe.get_doc("Solar Installation", name)
		doc.execution_start_date = doc.execution_start_date or doc.order_date
		frappe.db.set_value(
			"Solar Installation", name, "execution_start_date", doc.execution_start_date, update_modified=False
		)
		stages.sync_from_template(doc)
		stages.plan_dates(doc)
		for row in doc.stages:
			row.db_update()
