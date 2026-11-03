# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Tasks start together on the payment dates (seed_stages): the first payment's work on the
day it came, the half's work on the day half was in, the serials and the payment after
installation on the day the task before them is completed - each due its SLA later, with the
new SLAs and no due anchors.

The shared template takes the seed's SLAs and loses its anchors. On every running project the
two payment dates are filled in from what happened, a task that should have started by now
starts - dated the day its payment came - and every open task is due its SLA after its start.
Nothing done changes. An old job missing its lead is updated all the same.
"""

import frappe
from frappe.utils import add_days, getdate, today

from a3_sola.api import stages
from a3_sola.setup import install_ops
from a3_sola.setup.seed_stages import NEXT_AT_HALF, START_AT_HALF, START_ON_ADVANCE

DONE = ("Completed", "Skipped")


def execute():
	frappe.reload_doc("solar_operations", "doctype", "solar_installation")
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_log")
	install_ops.seed_stage_templates()
	frappe.db.sql("""update `tabInstallation Stage Log` set due_anchor_task = null, due_anchor_days = 0
		where ifnull(due_anchor_task, '') != ''""")

	for job in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", job)
		by_code = {r.stage_code: r for r in inst.stages}
		adv = by_code.get("ADV")
		if not inst.get("advance_received_on") and adv and adv.status != "Pending":
			inst.advance_received_on = adv.actual_start_date or (getdate(adv.payment_received_on)
				if adv.get("payment_received_on") else None) or today()
		# Half really in - or exempt: a job with no value yet is not held back, but has paid nothing.
		half_in = inst.get("half_payment_exempt") or (inst.get("gross_contract_value") and stages.half_paid_open(inst))
		if not inst.get("half_paid_on") and half_in:
			began = [getdate(r.actual_start_date) for r in inst.stages
				if r.stage_code in START_AT_HALF and r.actual_start_date]
			inst.half_paid_on = min(began) if began else today()

		started = []
		if inst.get("advance_received_on"):
			started += _start_on(inst, START_ON_ADVANCE, inst.advance_received_on)
		if inst.get("half_paid_on"):
			started += _start_on(inst, START_AT_HALF, inst.half_paid_on)
			for code, (before,) in NEXT_AT_HALF.items():
				prior = by_code.get(before)
				if prior and prior.status == "Completed" and prior.actual_completion_date:
					started += _start_on(inst, (code,), prior.actual_completion_date)

		stages.sync_from_template(inst)
		# Every open task is due its SLA after it started (no anchors any more).
		for row in inst.stages:
			if row.status not in DONE and row.actual_start_date:
				row.due_date = add_days(getdate(row.actual_start_date), int(row.sla_days or 0))
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_permissions = True
		inst.flags.ignore_mandatory = True
		inst.save()
		if started:
			try:
				stages.notify_started(inst, started)
			except Exception:
				frappe.log_error(title="Task flow patch: could not notify " + inst.name)


def _start_on(inst, codes, day):
	"""The pending tasks among `codes` started, dated `day` - the day their work could start."""
	rows = stages._start(inst, codes)
	for row in rows:
		row.actual_start_date = getdate(day)
		row.due_date = None
	return rows
