# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A dealer may not work Accept Customer (partner_scope.DEALER_BARRED_TASKS). Take dealers off
it on every project where it is still open; it is then for the company's staff to assign."""

import frappe


def execute():
	from a3_sola.api import partner_scope

	open_rows = frappe.get_all(
		"Installation Stage Log",
		filters={"parenttype": "Solar Installation", "stage_code": ["in", partner_scope.DEALER_BARRED_TASKS],
			"status": ["not in", ("Completed", "Skipped")]},
		fields=["name", "parent", "stage_code", "assigned_to"],
	)
	for row in open_rows:
		people = frappe.get_all(
			"Installation Task Assignee",
			filters={"parenttype": "Solar Installation", "parent": row.parent, "stage_code": row.stage_code},
			fields=["name", "user"], order_by="idx asc",
		)
		kept = []
		for person in people:
			if partner_scope.dealer_barred(row.stage_code, person.user):
				frappe.db.delete("Installation Task Assignee", person.name)
			else:
				kept.append(person.user)
		if row.assigned_to and partner_scope.dealer_barred(row.stage_code, row.assigned_to):
			frappe.db.set_value("Installation Stage Log", row.name, "assigned_to", kept[0] if kept else None,
				update_modified=False)
