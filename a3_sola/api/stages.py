# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The installation stage engine, and the extension points later phases register against.

Stages are configured, not coded. An Installation Stage Template defines the chain per
scheme, system type and consumer category, and a stage that does not apply to a given job
is created as Skipped with its reason recorded - never omitted, because an auditor asking
why there is no inspectorate certificate needs to see the answer on the record.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, today

from a3_sola.api.settings import get_value

MANAGER_ROLES = ("Solar Operations Manager", "System Manager")
EXTERNAL_OWNERS = ("DISCOM", "Inspectorate", "Bank", "Government")


# --------------------------------------------------------------- template resolution
def resolve_template(scheme=None, system_type=None, consumer_category=None, company=None):
	"""Best-matching stage template, falling back to the company default."""
	filters = {"is_active": 1}
	if company:
		filters["company"] = company

	candidates = frappe.get_all(
		"Installation Stage Template",
		filters=filters,
		fields=["name", "applicable_scheme", "applicable_system_type", "consumer_category", "is_default"],
	)
	if not candidates:
		frappe.throw(
			_("No active Installation Stage Template for {0}. A job cannot be executed without a stage chain.").format(
				company or _("this site")
			),
			title=_("Stage Template Missing"),
		)

	def score(row):
		points = 0
		if scheme and row.applicable_scheme == scheme:
			points += 4
		elif row.applicable_scheme:
			points -= 10
		if system_type and row.applicable_system_type in (system_type, "All"):
			points += 1
		if consumer_category and row.consumer_category in (consumer_category, "All"):
			points += 1
		if row.is_default:
			points += 1
		return points

	best = max(candidates, key=score)
	if score(best) < 0:
		default = next((c for c in candidates if c.is_default), None)
		if not default:
			frappe.throw(_("No stage template matches and no default is set."), title=_("Stage Template Missing"))
		return default.name
	return best.name


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
	"""Populate the stage log and the document checklist from the resolved template."""
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
				"sla_days": row.sla_days,
				"is_mandatory": row.is_mandatory,
				"planned_date": planned,
				"status": "Pending" if applies else "Skipped",
				"skip_reason": None if applies else reason,
			},
		)
		if applies and row.document_checklist_template:
			_append_checklist(installation, row.stage_code, row.document_checklist_template)

	return installation


def _append_checklist(installation, stage_code, checklist_template):
	template = frappe.get_cached_doc("Document Checklist Template", checklist_template)
	for item in template.items:
		installation.append(
			"documents",
			{
				"stage_code": stage_code,
				"document_name": item.document_name,
				"is_mandatory": item.is_mandatory,
				"solar_document_template": item.solar_document_template,
			},
		)


# ------------------------------------------------------------------- recomputation
def recompute(installation):
	"""Derive status, current stage, progress and breach flags. Never hand-set."""
	order_date = getdate(installation.order_date or today())
	installation.days_since_order = date_diff(today(), order_date)

	current = None
	blocked = False
	breached = False
	completed_mandatory = 0
	total_mandatory = 0

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

		row.is_sla_breached = (
			1 if row.sla_days and row.status in ("In Progress", "Blocked") and flt(row.days_in_stage) > flt(row.sla_days) else 0
		)
		if row.is_sla_breached:
			breached = True
		if row.status == "Blocked":
			blocked = True
		if current is None and row.status not in ("Completed", "Skipped"):
			current = row

	installation.is_sla_breached = 1 if breached else 0
	installation.current_stage = current.stage_name if current else None
	installation.current_stage_owner_type = current.owner_type if current else None
	installation.overall_progress_percent = (
		flt(completed_mandatory * 100.0 / total_mandatory, 2) if total_mandatory else 0
	)

	blocking = None
	if current and (blocked or current.is_sla_breached):
		blocking = current.owner_type
	installation.blocking_party = blocking

	installation.status = _derive_status(installation, current, blocked)
	return installation


def _derive_status(installation, current, blocked):
	if installation.docstatus == 2:
		return "Cancelled"
	if installation.docstatus == 0:
		return "Draft"

	done = {row.stage_code for row in installation.stages if row.status in ("Completed", "Skipped")}
	if not current:
		return "Closed"
	if blocked:
		return "Blocked"
	if "DBT" in done and _stage_status(installation, "DBT") == "Completed":
		return "Subsidy Claimed"
	if _stage_status(installation, "COMM") == "Completed":
		return "Commissioned"
	if current.owner_type in EXTERNAL_OWNERS:
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


# ------------------------------------------------------------------- transitions
@frappe.whitelist()
def advance_stage(installation, stage_code, actual_date=None, external_reference=None, remarks=None):
	"""Complete a stage and start the next.

	BLOCKS when any mandatory document for the stage is missing or unverified, naming each
	gap. Evidence before progress is the whole point of the chain.
	"""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	row = _get_stage(doc, stage_code)

	if row.status == "Completed":
		frappe.throw(_("Stage {0} is already complete.").format(stage_code))
	if row.status == "Skipped":
		frappe.throw(_("Stage {0} was skipped: {1}").format(stage_code, row.skip_reason or ""))

	missing = missing_documents(doc, stage_code)
	if missing:
		frappe.throw(
			_("Stage {0} cannot be completed. These documents are missing or unverified: {1}").format(
				frappe.bold(row.stage_name), "<br>- " + "<br>- ".join(missing)
			),
			title=_("Evidence Required"),
		)

	_check_gates(doc, stage_code)

	row.status = "Completed"
	row.actual_completion_date = getdate(actual_date or today())
	row.completed_by = frappe.session.user
	if external_reference:
		row.external_reference = external_reference
	if remarks:
		row.remarks = remarks
	if not row.actual_start_date:
		row.actual_start_date = row.actual_completion_date

	for nxt in doc.stages:
		if nxt.status == "Pending":
			nxt.status = "In Progress"
			nxt.actual_start_date = getdate(actual_date or today())
			break

	_save(doc, _("Stage {0} completed by {1}.").format(row.stage_name, frappe.session.user))
	notify_stage_completed(doc, stage_code)
	return doc.current_stage


def _check_gates(doc, stage_code):
	"""Gates that protect the client's vendor registration."""
	if stage_code == "PCR":
		blocking = frappe.get_all(
			"Installation Snag",
			filters={
				"solar_installation": doc.name,
				"severity": ["in", ["Critical", "Major"]],
				"status": ["in", ["Open", "In Progress"]],
				"docstatus": ["<", 2],
			},
			pluck="name",
		)
		if blocking:
			frappe.throw(
				_(
					"PCR cannot be filed while {0} critical or major snag(s) remain open: {1}. "
					"The ministry can temporarily deactivate a vendor over unresolved defects."
				).format(len(blocking), ", ".join(blocking)),
				title=_("Open Snags"),
			)

	if stage_code == "COMM" and get_value("require_serials_before_commissioning"):
		if not doc.serial_capture_complete:
			frappe.throw(
				_("Commissioning is blocked: {0} of {1} module serials captured. The national portal rejects submissions with missing or repeated serials.").format(
					doc.modules_captured or 0, doc.modules_expected or 0
				),
				title=_("Serial Capture Incomplete"),
			)


def missing_documents(doc, stage_code):
	"""Mandatory documents for a stage that are absent or unverified."""
	gaps = []
	for row in doc.documents:
		if row.stage_code != stage_code or not row.is_mandatory:
			continue
		if not row.attachment:
			gaps.append(_("{0} (not attached)").format(row.document_name))
		elif not row.is_verified:
			gaps.append(_("{0} (attached but not verified)").format(row.document_name))
	return gaps


@frappe.whitelist()
def block_stage(installation, stage_code, blocked_reason):
	if not (blocked_reason or "").strip():
		frappe.throw(_("A reason is mandatory when blocking a stage."))
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	row = _get_stage(doc, stage_code)
	row.status = "Blocked"
	row.blocked_reason = blocked_reason.strip()
	_save(doc, _("Stage {0} blocked: {1}").format(row.stage_name, blocked_reason.strip()))
	return doc.status


@frappe.whitelist()
def unblock_stage(installation, stage_code, remarks=None):
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	row = _get_stage(doc, stage_code)
	if row.status != "Blocked":
		frappe.throw(_("Stage {0} is not blocked.").format(stage_code))
	row.status = "In Progress"
	row.blocked_reason = None
	if remarks:
		row.remarks = remarks
	_save(doc, _("Stage {0} unblocked.").format(row.stage_name))
	return doc.status


@frappe.whitelist()
def skip_stage(installation, stage_code, reason):
	"""Manager-only, and refused for a mandatory stage."""
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when skipping a stage."))
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	row = _get_stage(doc, stage_code)
	if row.is_mandatory:
		_require_manager(_("skip a mandatory stage"))
	row.status = "Skipped"
	row.skip_reason = reason.strip()
	_save(doc, _("Stage {0} skipped: {1}").format(row.stage_name, reason.strip()))
	return doc.current_stage


@frappe.whitelist()
def revert_stage(installation, stage_code, reason):
	"""Manager-only. Clears this stage and every stage after it."""
	_require_manager(_("revert a stage"))
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when reverting a stage."))

	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	target = _get_stage(doc, stage_code)
	reached = False
	for row in doc.stages:
		if row.stage_code == stage_code:
			reached = True
		if not reached:
			continue
		row.status = "Pending"
		row.actual_start_date = None
		row.actual_completion_date = None
		row.completed_by = None
		row.blocked_reason = None
		row.days_in_stage = 0
		row.is_sla_breached = 0
	target.status = "In Progress"
	target.actual_start_date = today()
	_save(doc, _("Reverted to stage {0}: {1}").format(target.stage_name, reason.strip()))
	return doc.current_stage


def notify_stage_completed(doc, stage_code):
	"""Fan out to the phase extension points. Phase 3 registers against these."""
	if stage_code == "COMM":
		report = frappe.db.get_value(
			"Commissioning Report", {"solar_installation": doc.name, "docstatus": 1}, "name"
		)
		if report:
			on_commissioning_submitted(frappe.get_doc("Commissioning Report", report))


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
