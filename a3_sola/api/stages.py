# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The installation task engine's foundations, and the extension points Projects registers against.

Tasks are configured, not coded. One Installation Stage Template, shared by every company, lists the
tasks; a task that does not apply to a given job is created as Skipped with its reason
recorded - never omitted, because an auditor asking why there is no inspectorate certificate
needs to see the answer on the record.

This module builds and recomputes. Transitions - completing, skipping, blocking, linking a
task to the document that carries it out - live in `a3_sola.api.tasks`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, today

from a3_sola.api.settings import get_value

MANAGER_ROLES = ("Solar Operations Manager", "System Manager")
EXTERNAL_OWNERS = ("DISCOM", "Inspectorate", "Bank", "Government", "Contractor")
DONE = ("Completed", "Skipped")


# --------------------------------------------------------------- template resolution
def resolve_template(scheme=None, system_type=None, consumer_category=None, company=None):
	"""The task template: one, shared by every company.

	The parameters stay for the callers that pass them. Order: the shared active default
	(no company); else the template Settings names, if it is live and shared or the
	company's; else the company's own active default; else the only active one.
	"""
	shared = frappe.db.get_value("Installation Stage Template", {"is_shared": 1, "is_active": 1}, "name")
	if shared:
		return shared

	preferred = get_value("default_stage_template")
	if preferred:
		live = frappe.db.get_value(
			"Installation Stage Template", preferred, ["is_active", "company"], as_dict=True
		)
		if live and live.is_active and (not live.company or not company or live.company == company):
			return preferred

	filters = {"is_active": 1}
	if company:
		filters["company"] = ["in", [company, ""]]
	default = frappe.get_all(
		"Installation Stage Template", filters={**filters, "is_default": 1}, pluck="name", limit=1
	)
	if default:
		return default[0]

	active = frappe.get_all(
		"Installation Stage Template", filters=filters, pluck="name", order_by="creation asc"
	)
	if not active:
		frappe.throw(
			_("No active Installation Stage Template for {0}. A job cannot be executed without its tasks.").format(
				company or _("this site")
			),
			title=_("Task Template Missing"),
		)
	return active[0]


def stage_applies(row, context):
	"""Does this template row apply to this job?

	Returns (applies, reason). The reason is recorded on skipped stages.
	"""
	rule = row.applicability or "Always"
	if rule == "Always":
		return True, None
	if rule == "Financed Sales Only":
		return bool(context.get("is_financed")), _("Self-funded sale")
	if rule == "Self-Funded Only":
		return not context.get("is_financed"), _("Financed sale")
	if rule == "Subsidised Only":
		return bool(context.get("subsidy_scheme")), _("No subsidy scheme on this job")
	if rule == "Non-Subsidised Only":
		return not context.get("subsidy_scheme"), _("Subsidised job")
	if rule == "Above Capacity Threshold":
		threshold = flt(row.applicability_threshold_kw)
		applies = flt(context.get("capacity_kw")) > threshold
		return applies, _("Capacity {0} kW is at or below the {1} kW threshold").format(
			flt(context.get("capacity_kw")), threshold
		)
	if rule == "Net Meter From DISCOM Only":
		return context.get("net_meter_mode") == "Availed from DISCOM on Rental", _("Net meter purchased by the customer")
	if rule == "Net Meter Purchased Only":
		return context.get("net_meter_mode") != "Availed from DISCOM on Rental", _("Net meter availed from the DISCOM")
	return True, None


def build_stages(installation):
	"""Populate the task rows and the document register from the resolved template.

	Register rows are created for every task, skipped ones included: a skipped task can be
	un-skipped later, and its expected documents should already be waiting for it.
	"""
	template = frappe.get_cached_doc("Installation Stage Template", installation.stage_template)
	context = {
		"is_financed": installation.is_financed,
		"subsidy_scheme": installation.subsidy_scheme,
		"capacity_kw": installation.capacity_kw,
		"net_meter_mode": installation.net_meter_mode,
	}

	installation.set("stages", [])
	installation.set("documents", [])
	planned = getdate(installation.order_date or today())

	rows = sorted(template.stages, key=lambda r: (r.display_order or 0, r.idx))
	for row in rows:
		applies, reason = stage_applies(row, context)
		planned = add_days(planned, int(row.sla_days or 0))
		installation.append(
			"stages",
			{
				"stage_code": row.stage_code,
				"stage_name": row.stage_name,
				"owner_type": row.owner_type,
				"responsible_role": row.responsible_role,
				"task_doctype": row.task_doctype,
				"sla_days": row.sla_days,
				"is_mandatory": row.is_mandatory,
				"due_anchor_task": row.due_anchor_task,
				"due_anchor_days": row.due_anchor_days,
				"planned_date": planned,
				"status": "Pending" if applies else "Skipped",
				"skip_reason": None if applies else reason,
			},
		)
		# The shared template names no checklist; the job's company has its own.
		checklist = row.document_checklist_template or frappe.db.get_value(
			"Document Checklist Template",
			{"stage_code": row.stage_code, "company": installation.company},
			"name",
		)
		if checklist:
			_append_checklist(installation, row.stage_code, checklist)

	return installation


def _append_checklist(installation, stage_code, checklist_template):
	template = frappe.get_cached_doc("Document Checklist Template", checklist_template)
	for item in template.items:
		installation.append(
			"documents",
			{
				"stage_code": stage_code,
				"document_name": item.document_name,
				"document_kind": "Expected",
				"is_mandatory": item.is_mandatory,
				"solar_document_template": item.solar_document_template,
			},
		)


# ------------------------------------------------------------------- recomputation
def recompute(installation):
	"""Derive status, focus task, progress, due dates and overdue flags. Never hand-set.

	Tasks are a set, not a sequence, so the "current stage" is a focus, not a position:
	the first blocked task, else the first in progress, else the first still pending.
	"""
	order_date = getdate(installation.order_date or today())
	installation.days_since_order = date_diff(today(), order_date)
	by_code = {row.stage_code: row for row in installation.stages}

	breached = False
	completed_mandatory = 0
	total_mandatory = 0
	first_blocked = first_active = first_pending = first_breached = None

	for row in installation.stages:
		if row.is_mandatory and row.status != "Skipped":
			total_mandatory += 1
			if row.status == "Completed":
				completed_mandatory += 1

		if row.status == "In Progress" and row.actual_start_date:
			row.days_in_stage = date_diff(today(), getdate(row.actual_start_date))
		elif row.status == "Completed" and row.actual_start_date and row.actual_completion_date:
			row.days_in_stage = date_diff(getdate(row.actual_completion_date), getdate(row.actual_start_date))
		elif row.status in ("Pending", "Skipped"):
			row.days_in_stage = 0

		_derive_due_date(row, by_code)
		row.is_sla_breached = (
			1
			if row.status in ("In Progress", "Blocked") and row.due_date and getdate(today()) > getdate(row.due_date)
			else 0
		)
		if row.is_sla_breached:
			breached = True
			first_breached = first_breached or row
		if row.status == "Blocked":
			first_blocked = first_blocked or row
		elif row.status == "In Progress":
			first_active = first_active or row
		elif row.status == "Pending":
			first_pending = first_pending or row

	focus = first_blocked or first_active or first_pending
	installation.is_sla_breached = 1 if breached else 0
	installation.current_stage = focus.stage_name if focus else None
	installation.current_stage_owner_type = focus.owner_type if focus else None
	installation.overall_progress_percent = (
		flt(completed_mandatory * 100.0 / total_mandatory, 2) if total_mandatory else 0
	)

	blocking = first_blocked or first_breached
	installation.blocking_party = blocking.owner_type if blocking else None

	installation.status = _derive_status(installation, focus, bool(first_blocked))
	return installation


def _derive_due_date(row, by_code):
	"""When a task is due.

	An anchored task's window starts when its anchor completes - the thirty days for Form 2
	run from the Form 1 fee, not from the order - and that overrides anything else while the
	task is open. Otherwise the SLA runs from the day the task started, and a due date set
	by hand (assignment) is left alone.
	"""
	if row.due_anchor_task and row.status not in DONE:
		anchor = by_code.get(row.due_anchor_task)
		if anchor and anchor.status == "Completed" and anchor.actual_completion_date:
			row.due_date = add_days(getdate(anchor.actual_completion_date), int(row.due_anchor_days or 0))
			return
	if not row.due_date and row.actual_start_date and row.sla_days:
		row.due_date = add_days(getdate(row.actual_start_date), int(row.sla_days))


def _derive_status(installation, focus, blocked):
	if installation.docstatus == 2:
		return "Cancelled"
	if installation.docstatus == 0:
		return "Draft"

	rows = installation.stages
	open_mandatory = [r for r in rows if r.is_mandatory and r.status not in DONE]
	active = [r for r in rows if r.status in ("In Progress", "Blocked")]
	if not open_mandatory and not active:
		return "Closed"
	if blocked:
		return "Blocked"
	if _stage_status(installation, "DBT") == "Completed":
		return "Subsidy Claimed"
	if _stage_status(installation, "COMM") == "Completed":
		return "Commissioned"
	in_progress = [r for r in rows if r.status == "In Progress"]
	# Only when every task being worked on is somebody else's. "Any external" would hide
	# the internal work that is also waiting on this office.
	if in_progress and all(r.owner_type in EXTERNAL_OWNERS for r in in_progress):
		return "Awaiting External"
	return "In Progress"


def _stage_status(installation, stage_code):
	for row in installation.stages:
		if row.stage_code == stage_code:
			return row.status
	return None


def _get_stage(installation, stage_code):
	for row in installation.stages:
		if row.stage_code == stage_code:
			return row
	frappe.throw(_("Stage {0} is not on installation {1}.").format(stage_code, installation.name))


def _require_manager(action):
	if not set(frappe.get_roles()).intersection(MANAGER_ROLES):
		frappe.throw(
			_("Only {0} may {1}.").format(" or ".join(MANAGER_ROLES), action), frappe.PermissionError
		)


def _save(installation, message):
	recompute(installation)
	installation.flags.ignore_validate_update_after_submit = True
	installation.save(ignore_permissions=True)
	installation.add_comment("Comment", message)


# ================================================================ EXTENSION POINTS
# Implemented by Phase 3 (Solar Projects). Each delegates into `a3_sola.api.*`; none of
# them posts anything by itself, and all postings are gated inside `api.accounting`.
#
# Do NOT scatter TODO comments elsewhere - these five functions are the contract.
#
# Every one is wrapped: a failure in the money layer must never stop an operations user
# from commissioning a plant or recording a fee. It is logged loudly instead.


def _safely(handler, doc, event):
	try:
		return handler(doc)
	except Exception:
		if frappe.flags.in_test:
			# Graceful degradation is for production. A test that silently passes over a
			# broken money layer is worse than no test at all.
			raise
		frappe.log_error(frappe.get_traceback(), f"a3_sola: {event} failed for {doc.name}")
		frappe.msgprint(
			_("{0} was recorded, but the Projects module could not process it. "
			  "The error is logged; operations are unaffected.").format(_(doc.doctype)),
			title=_("Projects Step Failed"),
			indicator="orange",
		)
		return None


def on_commissioning_submitted(doc):
	"""A Commissioning Report was submitted.

	Creates the Project (with the whole solar context), its billing plan, and the five-year
	O&M contract with its visit calendar - then accrues the O&M provision.

	`doc.solar_installation` already carries warranty_start_date, warranty_end_date and the
	performance ratio at commissioning; the package and serial register hang off it.
	"""
	frappe.logger("a3_sola").info({"event": "on_commissioning_submitted", "doc": doc.name})
	from a3_sola.api import om

	return _safely(om.create_project_from_commissioning, doc, "on_commissioning_submitted")


def on_subsidy_claim_submitted(doc):
	"""A Subsidy Claim was submitted.

	Under "Company Funded Gap" this posts the receivable. Under "Customer Claims Directly"
	the company has funded nothing, so NO ENTRY IS REQUIRED and none is made - that absence
	is deliberate.
	"""
	frappe.logger("a3_sola").info({"event": "on_subsidy_claim_submitted", "doc": doc.name})
	from a3_sola.api import accounting

	return _safely(accounting.post_subsidy_receivable, doc, "on_subsidy_claim_submitted")


def on_subsidy_recovery_recorded(doc):
	"""The customer passed their DBT over. Settles the receivable."""
	frappe.logger("a3_sola").info({"event": "on_subsidy_recovery_recorded", "doc": doc.name})
	from a3_sola.api import accounting

	return _safely(accounting.post_subsidy_recovery, doc, "on_subsidy_recovery_recorded")


def on_statutory_fee_recorded(doc):
	"""A statutory fee was paid. Raises the reimbursement receivable where the company paid.

	A fee the customer paid directly posts nothing - it is recorded for reporting only.
	"""
	frappe.logger("a3_sola").info({"event": "on_statutory_fee_recorded", "doc": doc.name})
	from a3_sola.api import accounting

	result = _safely(accounting.post_statutory_receivable, doc, "on_statutory_fee_recorded")
	_sync_statutory_recovery(doc)
	return result


def on_statutory_refund_received(doc):
	"""A registration refund landed. Settles the receivable, or records that it reached the consumer."""
	frappe.logger("a3_sola").info({"event": "on_statutory_refund_received", "doc": doc.name})
	from a3_sola.api import accounting

	result = _safely(accounting.post_statutory_refund, doc, "on_statutory_refund_received")
	_sync_statutory_recovery(doc)
	return result


def _sync_statutory_recovery(payment):
	"""Keep the Projects-side recovery record in step with the Operations-side payment."""
	project = frappe.db.get_value("Solar Installation", payment.solar_installation, "project")
	if not project:
		return None
	try:
		from a3_sola.api import recovery

		return recovery.sync_from_payment(payment, project)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: statutory recovery sync {payment.name}")
		return None
