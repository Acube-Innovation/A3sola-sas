# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The job's payment schedule is kept on its billing plan: each milestone knows its payment
task (ADV, BAL, PCOM) and credit days, and the payments received are rows of the plan.

Every plan takes its milestones' phase and credit days from its template; each job's payment
already recorded on its payment task's row (or on an older payment Installation Task) moves
onto the plan - confirmed if the task is done, awaiting Accounts if it is still with them - and
a task done before amounts were recorded counts its phase paid in full, as the schedule read
it. Then every plan's standing is worked out (billing.recompute_payments).
"""

import frappe
from frappe.utils import flt, getdate, today

from a3_sola.api import billing

PHASES = ("ADV", "BAL", "PCOM")


def execute():
	for doctype in ("billing_plan_payment", "billing_milestone_entry", "solar_billing_plan"):
		frappe.reload_doc("solar_projects", "doctype", doctype)
	for name in frappe.get_all("Solar Billing Plan", filters={"docstatus": ["<", 2]}, pluck="name"):
		plan = frappe.get_doc("Solar Billing Plan", name)
		phases(plan)
		if plan.solar_installation and frappe.db.exists("Solar Installation", plan.solar_installation):
			payments(plan, frappe.get_doc("Solar Installation", plan.solar_installation))
		billing.recompute_summary(plan)
		plan.flags.ignore_validate_update_after_submit = True
		plan.flags.ignore_permissions = True
		plan.flags.ignore_links = True
		plan.save(ignore_permissions=True)


def phases(plan):
	"""Each milestone's payment task and credit days, from the plan's template (by name, else
	by position)."""
	rows = frappe.get_all("Billing Milestone Template Detail", filters={"parent": plan.milestone_template,
		"parenttype": "Billing Milestone Template"}, fields=["milestone_name", "is_advance", "credit_days"],
		order_by="idx asc") if plan.milestone_template else []
	if not rows:
		return
	codes = billing.phase_codes(rows)
	by_name = {r.milestone_name: (code, r) for r, code in zip(rows, codes)}
	for i, row in enumerate(plan.milestones):
		code, source = by_name.get(row.milestone_name) or ((codes[i], rows[i]) if i < len(rows) else (None, None))
		if code and not row.phase_code:
			row.phase_code = code
		if source and not row.credit_days:
			row.credit_days = int(source.credit_days or 0)


def payments(plan, inst):
	"""The job's payments recorded before the plan held them, onto the plan."""
	stages = {r.stage_code: r for r in inst.stages}
	for code in PHASES:
		if any(p.phase_code == code for p in plan.get("payments") or []):
			continue
		row = stages.get(code)
		if not row or row.status == "Skipped":
			continue
		receipt = next((d.attachment for d in inst.documents if d.stage_code == code and d.attachment), None)
		done = row.status == "Completed"
		if flt(row.get("payment_amount")) and (done or row.get("payment_received_by")):
			plan.append("payments", {
				"phase_code": code, "amount": flt(row.payment_amount),
				"payment_date": getdate(row.payment_received_on or row.actual_completion_date or today()),
				"bank": row.payment_bank, "receiving_firm": row.payment_company, "account": row.payment_account,
				"receipt": receipt, "status": "Confirmed" if done else "Awaiting Confirmation",
				"recorded_by": row.payment_received_by, "recorded_on": row.payment_received_on,
				"confirmed_by": row.completed_by if done else None,
				"remarks": "Moved from the payment task when the schedule moved onto the plan.",
			})
			continue
		if not done:
			continue
		task = frappe.db.get_value("Installation Task", {"solar_installation": inst.name, "task_code": code,
			"docstatus": 1, "status": "Completed"}, ["amount", "paid_on", "payment_mode", "payment_reference"],
			as_dict=True) if code in ("ADV", "BAL") else None
		# Confirmed before amounts were recorded: the phase in full, as the schedule assumed.
		amount = flt(task.amount) if task and flt(task.amount) else flt(sum(
			flt(m.milestone_amount) for m in plan.milestones if m.phase_code == code), 2)
		if not amount:
			continue
		plan.append("payments", {
			"phase_code": code, "amount": amount,
			"payment_date": getdate((task and task.paid_on) or row.actual_completion_date or today()),
			"payment_mode": (task and task.payment_mode) or None, "reference_no": (task and task.payment_reference) or None,
			"receipt": receipt, "status": "Confirmed", "confirmed_by": row.completed_by,
			"remarks": "Moved from the payment task when the schedule moved onto the plan.",
		})
