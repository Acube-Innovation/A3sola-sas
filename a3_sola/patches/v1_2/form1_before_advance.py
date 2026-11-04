# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 1 ahead of the advance, and asking for the advance (api/payment_followup).

On every running project the customer pays (not financed) whose advance has not come, Form 1
starts today if it is still waiting, as it now does with the order. A project already past
the point of asking - Form 1 submitted on a job the customer pays, the loan sanctioned on a
bank-loan job - with the advance still owed is due to be asked from that day.
"""

import frappe

from a3_sola.api import payment_followup, stages


def execute():
	frappe.reload_doc("solar_operations", "doctype", "payment_follow_up")
	frappe.reload_doc("solar_operations", "doctype", "solar_installation")
	frappe.reload_doc("solar_crm", "doctype", "a3_sola_settings")

	for job in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", job)
		adv = next((r for r in inst.stages if r.stage_code == "ADV"), None)
		if not adv or adv.status in ("Completed", "Skipped"):
			continue
		started = [] if inst.get("advance_received_on") else stages.start_form1_early(inst)
		due = None
		if not inst.get("advance_followup_due_on") and payment_followup.started(inst) and payment_followup.is_open(inst):
			due = payment_followup.first_due(inst)
		if not (started or due):
			continue
		if due:
			inst.advance_followup_due_on = due
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.flags.ignore_mandatory = True
		inst.save()
		if started:
			inst.add_comment("Comment", "Form 1 started ahead of the advance (the customer pays this project).")
			try:
				stages.notify_started(inst, started)
			except Exception:
				frappe.log_error(title="Form 1 before advance patch: could not notify " + inst.name)
