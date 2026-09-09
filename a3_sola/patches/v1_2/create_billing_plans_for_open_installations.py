# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every open job gets its billing plan, with what has already happened replayed quietly.

Plans used to be created at commissioning, so a job between the order and commissioning
had no plan and its advance milestone never fired. From now on the plan is created at the
order; this gives the jobs already in flight theirs, fires the milestones of tasks they
have completed without raising accounts ToDos or auto-invoices, and leaves jobs that
cannot carry a plan yet (no customer, no contract value) alone.
"""

import frappe


def execute():
	from a3_sola.api import billing

	created = skipped = 0
	for name in frappe.get_all(
		"Solar Installation",
		filters={"docstatus": 1, "status": ["not in", ["Closed", "Cancelled"]]},
		pluck="name",
	):
		if frappe.db.exists("Solar Billing Plan", {"solar_installation": name, "docstatus": ["<", 2]}):
			continue
		frappe.db.savepoint("a3s_plan")
		try:
			if billing.ensure_plan_for_installation(name, replay=True):
				created += 1
			else:
				skipped += 1
		except Exception:
			frappe.db.rollback(save_point="a3s_plan")
			skipped += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: billing plan for {name}")
	frappe.db.commit()
	print(f"a3_sola: {created} billing plan(s) created for open installations; {skipped} left without one")
	return {"created": created, "skipped": skipped}
