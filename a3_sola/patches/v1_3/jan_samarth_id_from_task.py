# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Loan applications take the Jan Samarth ID from the job's Jan Samarth task (its Jan Samarth
Reference): the jobs whose task already has one get it now, on the job and on each loan
application still without one."""

import frappe

from a3_sola.solar_operations.doctype.installation_task.installation_task import share_jan_samarth_id


def execute():
	for row in frappe.get_all("Installation Task", filters={"task_code": "DAL", "docstatus": ["<", 2],
			"approval_reference": ["is", "set"]}, fields=["solar_installation", "approval_reference"], order_by="modified asc"):
		reference = (row.approval_reference or "").strip()
		if row.solar_installation and reference:
			share_jan_samarth_id(row.solar_installation, reference)
	frappe.db.commit()
