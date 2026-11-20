# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Write each template task's Starts When as the app has started it (stages.default_trigger),
so Administration > Task Assignees shows the rule, and an admin can change it from there."""

import frappe


def execute():
	from a3_sola.api.stages import default_trigger

	for row in frappe.get_all("Installation Stage Template Detail", filters={"parenttype": "Installation Stage Template"},
			fields=["name", "stage_code", "start_trigger"]):
		if row.start_trigger:
			continue
		trigger, after = default_trigger(row.stage_code)
		frappe.db.set_value("Installation Stage Template Detail", row.name,
			{"start_trigger": trigger, "start_after_task": after}, update_modified=False)
	frappe.clear_cache(doctype="Installation Stage Template")
