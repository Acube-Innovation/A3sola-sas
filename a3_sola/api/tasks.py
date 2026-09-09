# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Task transitions, and the one hook that lets documents drive them.

A task is carried out in a document - a fee payment, a portal application, a work order -
and the installation's task row records which one. So there are two ways a row changes:
somebody acts on the installation directly (complete by hand, skip, block, assign), or the
document that owns the task is saved, submitted or cancelled and `sync_from_document` reads
the row's new state off it.

The second is the normal path and it is declarative: `TASK_DOCTYPES` says, per doctype,
which task codes a document owns and when it counts as Completed. Nothing in a controller
advances a task any more; the eight hand-rolled guards that used to are gone.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from a3_sola.api import stages
from a3_sola.api.settings import get_value
from a3_sola.api.stages import DONE, _get_stage, _require_manager, _save

#: Portal application types that carry a task, and which. Held here so the Portal
#: Application controller and the Task button read one map.
PORTAL_TASKS = {"National Portal": "NPA", "Electrical Inspectorate": "CEIG"}
FEE_TASKS = {"Application Fee": "F1PAY", "Registration Fee": "F2PAY", "Net Meter Charge": "MTRPAY"}
WORK_ORDER_TASKS = {"Structure": "IWOS", "Installation": "IWOI"}
PACK_TASKS = {"KSEB Submission": "KFORMS", "Bank Completion Pack": "BCOM", "Customer Completion File": "CFILE"}


# ------------------------------------------------------------------ the rules
def _first(doc, *fields):
	for field in fields:
		value = doc.get(field)
		if value:
			return value
	return None


def _submitted(doc):
	return cint(doc.get("docstatus")) == 1


def _work_order_codes(doc):
	kind = doc.get("work_order_kind")
	if kind in WORK_ORDER_TASKS:
		return [WORK_ORDER_TASKS[kind]]
	if kind:
		return []  # Rectification carries no task
	# Before the kind existed: the type said what the order was.
	return ["IWOS"] if doc.get("work_order_type") == "Structure Erection" else ["IWOI"]


def _subsidy_state(doc, code):
	status = doc.get("claim_status")
	if code == "SUBREQ":
		# The claim is the request. Submitting it is asking for the subsidy.
		return "Completed" if _submitted(doc) else "In Progress"
	if code == "CORR":
		if status in ("Query Raised", "Rejected"):
			return "Blocked"
		corrections = doc.get("corrections") or []
		if corrections:
			return (
				"Completed"
				if all(r.get("correction_done") and r.get("resubmitted_on") for r in corrections)
				else "In Progress"
			)
		if status in ("Approved", "Disbursed"):
			return "Skipped"
		# A correction only exists once something is queried; until then the row just
		# knows which claim it belongs to.
		return "Pending"
	if code == "DBT":
		return "Completed" if status == "Disbursed" and doc.get("disbursed_on") else "In Progress"
	return "In Progress"


def _review_state(doc, code):
	if code == "REVIEW":
		return "Completed" if _submitted(doc) and doc.get("status") == "Completed" else "In Progress"
	google = doc.get("google_review_status")
	if google == "Posted":
		return "Completed"
	if google == "Declined":
		return "Skipped"
	return "In Progress"


def _portal_state(doc, code):
	status = doc.get("application_status")
	if status == "Approved":
		return "Completed"
	if status == "Query Raised" and any(not q.get("is_resolved") for q in doc.get("queries") or []):
		return "Blocked"
	return "In Progress"


def _portal_reason(doc, code):
	query = next((q for q in doc.get("queries") or [] if not q.get("is_resolved")), None)
	return _("Query on {0}: {1}").format(doc.name, query.get("query_description")) if query else None


def _generic_state(doc, code):
	"""A submitted document whose own status says Completed - the shape of every task doc."""
	if not _submitted(doc):
		return "In Progress"
	status = doc.get("status")
	if status == "Skipped":
		return "Skipped"
	if status in (None, "Completed"):
		return "Completed"
	return "In Progress"


TASK_DOCTYPES = {
	"Installation Task": {
		"codes": lambda d: [d.task_code] if d.get("task_code") and d.task_code != "OTHER" else [],
		"state": _generic_state,
		"date": lambda d, c: _first(d, "completed_on"),
		"reference": lambda d, c: _first(d, "payment_reference", "certificate_no", "meter_serial", "ae_acknowledgement_no"),
		"cost": lambda d, c: flt(_first(d, "cost", "amount", "meter_cost")),
		"reason": lambda d, c: d.get("skip_reason"),
		"route": lambda inst, c: {"task_code": c},
	},
	"Sales Order": {
		"codes": lambda d: ["ORD"],
		"state": lambda d, c: "Completed" if _submitted(d) else "In Progress",
		"date": lambda d, c: d.get("transaction_date"),
		"reference": lambda d, c: d.name,
	},
	"Portal Application": {
		"codes": lambda d: [PORTAL_TASKS[d.application_type]] if d.get("application_type") in PORTAL_TASKS else [],
		"state": _portal_state,
		"date": lambda d, c: _first(d, "approval_date", "status_updated_on"),
		"reference": lambda d, c: _first(d, "approval_number", "application_number"),
		"reason": _portal_reason,
		"route": lambda inst, c: {"application_type": next(k for k, v in PORTAL_TASKS.items() if v == c)},
	},
	"Loan Application": {
		"codes": lambda d: ["LOAN"],
		"state": lambda d, c: "Completed" if _submitted(d) else "In Progress",
		"date": lambda d, c: _first(d, "sanctioned_on", "application_date"),
		"reference": lambda d, c: _first(d, "loan_sanction_no", "jan_samarth_id"),
	},
	"Solar Agreement": {
		"codes": lambda d: ["STMP"],
		"state": lambda d, c: "Completed" if d.get("stamp_paper_status") == "Purchased" else "In Progress",
		"date": lambda d, c: d.get("stamp_paper_purchased_on"),
		"reference": lambda d, c: d.get("stamp_paper_serial"),
		"cost": lambda d, c: flt(d.get("stamp_paper_value")),
	},
	"Installation Work Order": {
		"codes": _work_order_codes,
		"state": _generic_state,
		"date": lambda d, c: _first(d, "actual_end_date", "actual_completion_date", "completed_on"),
		"route": lambda inst, c: {
			"work_order_kind": next(k for k, v in WORK_ORDER_TASKS.items() if v == c),
			"work_order_type": "Structure Erection" if c == "IWOS" else "Module Mounting",
		},
	},
	"Statutory Fee Payment": {
		"codes": lambda d: [FEE_TASKS[d.fee_type]] if d.get("fee_type") in FEE_TASKS else [],
		"state": lambda d, c: "Completed" if _submitted(d) else "In Progress",
		"date": lambda d, c: d.get("payment_date"),
		"reference": lambda d, c: _first(d, "payment_reference", "receipt_no", "transaction_reference"),
		"cost": lambda d, c: flt(_first(d, "amount_gross", "amount")),
		"route": lambda inst, c: {"fee_type": next(k for k, v in FEE_TASKS.items() if v == c)},
	},
	"Commissioning Report": {
		"codes": lambda d: ["COMM"],
		"state": lambda d, c: "Completed" if _submitted(d) else "In Progress",
		"date": lambda d, c: d.get("commissioning_date"),
		"reference": lambda d, c: d.get("commissioning_certificate_no"),
	},
	"Subsidy Claim": {
		"codes": lambda d: ["SUBREQ", "CORR", "DBT"],
		"state": _subsidy_state,
		"date": lambda d, c: {"SUBREQ": d.get("pcr_uploaded_on"), "DBT": d.get("disbursed_on")}.get(c),
		"reference": lambda d, c: {"SUBREQ": d.get("pcr_reference_no"), "DBT": d.get("disbursement_reference")}.get(c),
		"reason": lambda d, c: _("No correction was needed") if c == "CORR" else None,
	},
	"Purchase Order": {
		"codes": lambda d: ["PROC"],
		"state": lambda d, c: "Completed" if _submitted(d) else "In Progress",
		"date": lambda d, c: d.get("transaction_date"),
		"reference": lambda d, c: d.name,
		"cost": lambda d, c: flt(d.get("grand_total")),
	},
	"Delivery Note": {
		"codes": lambda d: ["DISP"],
		"state": lambda d, c: "Completed" if _submitted(d) else "In Progress",
		"date": lambda d, c: d.get("posting_date"),
		"reference": lambda d, c: d.name,
	},
	"Document Pack": {
		"codes": lambda d: [PACK_TASKS[d.pack_type]] if d.get("pack_type") in PACK_TASKS else [],
		"state": _generic_state,
		"date": lambda d, c: _first(d, "completed_on", "acknowledged_on", "sent_to_bank_on", "handed_over_on"),
		"reference": lambda d, c: _first(d, "ae_acknowledgement_no", "bank_reference"),
		"cost": lambda d, c: flt(d.get("task_cost")),
		"route": lambda inst, c: {"pack_type": next(k for k, v in PACK_TASKS.items() if v == c)},
	},
	"Material Dispatch Notice": {
		"codes": lambda d: ["MATL"],
		"state": _generic_state,
		"date": lambda d, c: _first(d, "sent_on", "dispatch_date"),
		"reference": lambda d, c: d.get("sent_to"),
	},
	"Customer Review": {
		"codes": lambda d: ["REVIEW", "GREV"],
		"state": _review_state,
		"date": lambda d, c: d.get("google_review_posted_on") if c == "GREV" else d.get("review_date"),
		"reason": lambda d, c: d.get("decline_reason") if c == "GREV" else None,
	},
}


def task_codes_for(doc):
	rule = TASK_DOCTYPES.get(doc.doctype)
	return list(rule["codes"](doc)) if rule else []


def code_for(doc):
	codes = task_codes_for(doc)
	return codes[0] if codes else None


# ------------------------------------------------------------------ the hook
def sync_from_document(doc, method=None):
	"""Read the task row's state off the document that owns it.

	Fired on save, submit, update-after-submit and cancel of every executing doctype. A
	document claims its row the first time it is saved (Pending -> In Progress, or an
	un-skip), completes it per the doctype's rule, and gives it back on cancel. A row already
	held by another live document of the same doctype is left alone - two drafts for one
	task is a question for a person, not something to resolve by last-write-wins.
	"""
	rule = TASK_DOCTYPES.get(doc.doctype)
	if not rule:
		return None
	installation = doc.get(rule.get("installation_field", "solar_installation"))
	if not installation or not frappe.db.exists("Solar Installation", installation):
		return None
	codes = rule["codes"](doc)
	if not codes:
		return None

	from a3_sola.api import documents

	cancelling = method in ("on_cancel", "on_trash") or cint(doc.get("docstatus")) == 2
	inst = frappe.get_doc("Solar Installation", installation, for_update=True)
	if doc.get("company") and inst.company and doc.company != inst.company:
		# A document filed under another company never drives this job's rows - the
		# controller's company check refuses it, but a doc_event runs even when validation
		# was skipped, and an isolation probe must not leave its fingerprints here.
		return
	changed, completed_now = [], []
	for code in codes:
		row = _row(inst, code)
		if not row:
			continue
		if cancelling:
			if row.task_document == doc.name and row.task_doctype == doc.doctype:
				_release(row)
				changed.append(code)
			continue
		if _held_by_another(row, doc):
			continue
		if _apply(row, doc, code, rule):
			changed.append(code)
			if row.status == "Completed" and code not in completed_now and row.get("_completed_now"):
				completed_now.append(code)

	# Files register on every save, status change or not: an upload added to a task that
	# already started is the common case, and it must reach the register too.
	if cancelling:
		files_changed = documents.unregister_document(inst, doc.doctype, doc.name, save=False)
	else:
		files_changed = documents.register_attachments(inst, doc, codes[0], save=False)

	if not changed and not files_changed:
		return None
	if changed:
		message = _("Task {0}: {1} via {2} {3}").format(
			", ".join(changed), _("released") if cancelling else _row(inst, changed[0]).status, _(doc.doctype), doc.name
		)
	else:
		message = _("Documents {0} from {1} {2}").format(
			_("removed") if cancelling else _("registered"), _(doc.doctype), doc.name
		)
	_save(inst, message)
	for code in completed_now:
		notify_task_completed(inst, code)
	return changed


def _row(installation, code):
	return next((r for r in installation.stages if r.stage_code == code), None)


def _held_by_another(row, doc):
	if not row.task_document or row.task_document == doc.name or row.task_doctype != doc.doctype:
		return False
	live = frappe.db.get_value(row.task_doctype, row.task_document, "docstatus")
	return live is not None and cint(live) < 2


def _apply(row, doc, code, rule):
	"""Write one document's state onto one row. Returns whether anything changed."""
	before = (row.status, row.task_document, row.cost, row.actual_completion_date, row.blocked_reason)
	state = rule["state"](doc, code)
	was = row.status

	row.task_doctype = doc.doctype
	row.task_document = doc.name
	if not row.actual_start_date:
		row.actual_start_date = getdate(doc.get("creation") or today())
	if doc.get("assigned_to"):
		row.assigned_to = doc.assigned_to
	if rule.get("cost"):
		cost = rule["cost"](doc, code)
		if cost:
			row.cost = flt(cost)

	row.set("_completed_now", False)
	if state == "Completed":
		if was != "Completed":
			row.set("_completed_now", True)
		row.status = "Completed"
		row.actual_completion_date = getdate(_date(rule, doc, code) or today())
		row.completed_by = frappe.session.user
		row.external_reference = _reference(rule, doc, code) or row.external_reference
		row.blocked_reason = None
		row.skip_reason = None
	elif state == "Skipped":
		if was != "Completed":
			row.status = "Skipped"
			row.skip_reason = _reason(rule, doc, code) or row.skip_reason or _("Not required")
	elif state == "Blocked":
		if was != "Completed":
			row.status = "Blocked"
			row.blocked_reason = _reason(rule, doc, code) or row.blocked_reason
	elif state == "Pending":
		# Linked, not started: the document owns the row but has nothing to do on it yet.
		if was == "Skipped":
			row.status = "Pending"
			row.skip_reason = None
	else:
		if was in ("Pending", "Skipped"):
			row.status = "In Progress"
			row.skip_reason = None
		# Completed is never downgraded by a save; Blocked is released by unblock or approval.
	after = (row.status, row.task_document, row.cost, row.actual_completion_date, row.blocked_reason)
	return before != after


def release_dangling_links(installation, save=False):
	"""Rows whose document no longer exists let go of it.

	A task document can vanish outside the engine's hearing - a hard delete, a purge, a
	test fixture's cleanup - and a Dynamic Link to nothing makes the whole installation
	unsaveable. The row keeps its status and history; only the pointer is dropped, and a
	comment says which document went. Returns the rows released.
	"""
	inst = (
		frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	)
	released = []
	for row in inst.stages:
		if not (row.task_doctype and row.task_document):
			continue
		if frappe.db.exists("DocType", row.task_doctype) and frappe.db.exists(row.task_doctype, row.task_document):
			continue
		released.append(f"{row.stage_code}: {row.task_doctype} {row.task_document}")
		row.task_document = None
		if row.status == "In Progress":
			row.status = "Pending"
	for reg in inst.documents:
		if reg.source_doctype and reg.source_document and not (
			frappe.db.exists("DocType", reg.source_doctype) and frappe.db.exists(reg.source_doctype, reg.source_document)
		):
			reg.source_doctype = None
			reg.source_document = None
	if released and save:
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
	if released and not inst.is_new():
		inst.add_comment(
			"Comment",
			_("Task document(s) no longer exist and were unlinked: {0}").format("; ".join(released)),
		)
	return released


def _release(row):
	row.status = "Pending"
	row.task_document = None
	row.actual_completion_date = None
	row.completed_by = None
	row.external_reference = None
	row.cost = 0
	row.blocked_reason = None


def _date(rule, doc, code):
	return rule["date"](doc, code) if rule.get("date") else None


def _reference(rule, doc, code):
	return rule["reference"](doc, code) if rule.get("reference") else None


def _reason(rule, doc, code):
	return rule["reason"](doc, code) if rule.get("reason") else None


# ------------------------------------------------------------------ after completion
def notify_task_completed(installation, task_code):
	"""The single extension point for anything that happens because a task finished.

	Billing milestones keyed to a task fire from here; the Form 2 window starts from here.
	Every handler is wrapped: the money layer must never undo an operations user's work.
	"""
	handler = AFTER_COMPLETE.get(task_code)
	if handler:
		stages._safely(lambda doc: handler(doc, task_code), installation, f"after {task_code}")
	try:
		from a3_sola.api import billing

		stages._safely(
			lambda doc: billing.on_stage_completed(doc.name, task_code), installation, f"billing after {task_code}"
		)
	except ImportError:
		pass


def _start_form2_window(installation, task_code):
	"""Paying the Form 1 fee starts the thirty days for Form 2. The KFORMS row's due date
	follows from `recompute`; the installation carries the date for reports and reminders."""
	row = _row(installation, task_code)
	days = cint(get_value("form2_window_days")) or 30
	due = add_days(getdate(row.actual_completion_date or today()), days)
	installation.db_set("form2_due_on", due, update_modified=False)


AFTER_COMPLETE = {"F1PAY": _start_form2_window}


# ------------------------------------------------------------------ the Task button
@frappe.whitelist()
def open_task(installation, task_code=None):
	"""Where to go to do a task: its document if it has one, else what to create.

	Returns `{"doctype", "name", "route_options"}`. `name` set means open it; `name` None
	with `route_options` means make a new one prefilled; both None means there is nothing
	to open (an order task on a job that has no sales order).
	"""
	if not task_code:
		frappe.throw(_("Which task?"))
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	row = _get_stage(inst, task_code)
	doctype = row.task_doctype
	if not doctype:
		frappe.throw(_("Task {0} names no document to be carried out in.").format(task_code))

	if row.task_document and frappe.db.exists(doctype, row.task_document):
		if cint(frappe.db.get_value(doctype, row.task_document, "docstatus")) < 2:
			return {"doctype": doctype, "name": row.task_document, "route_options": None}

	existing = find_existing(inst, task_code, doctype)
	if existing:
		return {"doctype": doctype, "name": existing, "route_options": None}

	if doctype == "Sales Order":
		return {"doctype": doctype, "name": inst.sales_order or None, "route_options": None}

	rule = TASK_DOCTYPES.get(doctype) or {}
	route_options = {
		"solar_installation": inst.name,
		"solar_consumer": inst.solar_consumer,
		"company": inst.company,
		"task_code": task_code,
	}
	if rule.get("route"):
		route_options.update(rule["route"](inst, task_code))

	if doctype == "Statutory Fee Payment" and cint(get_value("auto_create_fee_payment_on_stage")):
		return {"doctype": doctype, "name": _draft_fee_payment(inst, route_options), "route_options": None}
	return {"doctype": doctype, "name": None, "route_options": route_options}


def find_existing(installation, task_code, doctype):
	"""A live document of `doctype` for this installation that owns `task_code` but is not
	yet linked - one somebody created from the list view rather than the Task button."""
	rule = TASK_DOCTYPES.get(doctype)
	if not rule or not frappe.db.exists("DocType", doctype):
		return None
	field = rule.get("installation_field", "solar_installation")
	if not frappe.get_meta(doctype).has_field(field):
		return None
	for name in frappe.get_all(
		doctype, filters={field: installation.name, "docstatus": ["<", 2]}, pluck="name", order_by="creation desc"
	):
		doc = frappe.get_doc(doctype, name)
		if task_code in rule["codes"](doc):
			return name
	return None


def _draft_fee_payment(installation, route_options):
	"""Settings `auto_create_fee_payment_on_stage`: the Task button inserts the draft itself,
	prefilled, so it shows in Connections at once and the amount is already resolved."""
	doc = frappe.new_doc("Statutory Fee Payment")
	doc.update(
		{
			"solar_installation": installation.name,
			"solar_consumer": installation.solar_consumer,
			"company": installation.company,
			"fee_type": route_options.get("fee_type"),
			"paid_by": "Company on Behalf of Customer",
			"payment_date": today(),
		}
	)
	if doc.meta.has_field("assigned_to"):
		doc.assigned_to = frappe.session.user
	doc.insert()
	return doc.name


# ------------------------------------------------------------------ transitions by hand
@frappe.whitelist()
def complete_task(installation, task_code=None, actual_date=None, remarks=None, cost=None,
                  external_reference=None, silent=False):
	"""Mark a task done without a document.

	For tasks that genuinely have no paperwork, and for managers tidying up. Refused when a
	live document already holds the task - complete that instead, so the record says what
	did the work - unless the caller is a manager.
	"""
	if not task_code:
		frappe.throw(_("Which task?"))
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	if row.status == "Completed":
		frappe.throw(_("Task {0} is already complete.").format(task_code))
	if row.task_document and _live(row):
		if not set(frappe.get_roles()).intersection(stages.MANAGER_ROLES):
			frappe.throw(
				_("Task {0} is being carried out in {1}. Complete it there.").format(
					task_code, frappe.utils.get_link_to_form(row.task_doctype, row.task_document)
				),
				title=_("Complete the Document"),
			)
	row.status = "Completed"
	row.actual_completion_date = getdate(actual_date or today())
	row.completed_by = frappe.session.user
	if not row.actual_start_date:
		row.actual_start_date = row.actual_completion_date
	if external_reference:
		row.external_reference = external_reference
	if remarks:
		row.remarks = remarks
	if cost is not None:
		row.cost = flt(cost)
	row.blocked_reason = None
	row.skip_reason = None
	_save(doc, _("Task {0} completed by {1}.").format(row.stage_name, frappe.session.user))
	if not cint(silent):
		notify_task_completed(doc, task_code)
	return doc.current_stage


@frappe.whitelist()
def skip_task(installation, task_code=None, reason=None):
	"""Not required on this job. Manager-only when the task is mandatory."""
	if not task_code:
		frappe.throw(_("Which task?"))
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when skipping a task."))
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	if row.status == "Completed":
		frappe.throw(_("Task {0} is already complete.").format(task_code))
	if row.task_document and _live(row):
		frappe.throw(
			_("Task {0} has a document, {1}. Cancel or delete it before skipping the task.").format(
				task_code, frappe.utils.get_link_to_form(row.task_doctype, row.task_document)
			)
		)
	if row.is_mandatory:
		_require_manager(_("skip a mandatory task"))
	row.status = "Skipped"
	row.skip_reason = reason.strip()
	row.blocked_reason = None
	_save(doc, _("Task {0} skipped: {1}").format(row.stage_name, reason.strip()))
	return doc.current_stage


@frappe.whitelist()
def unskip_task(installation, task_code=None, remarks=None):
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	if row.status != "Skipped":
		frappe.throw(_("Task {0} is not skipped.").format(task_code))
	row.status = "Pending"
	row.skip_reason = None
	if remarks:
		row.remarks = remarks
	_save(doc, _("Task {0} put back.").format(row.stage_name))
	return doc.current_stage


@frappe.whitelist()
def block_task(installation, task_code=None, reason=None):
	if not task_code:
		frappe.throw(_("Which task?"))
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when blocking a task."))
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	if row.status in DONE:
		frappe.throw(_("Task {0} is {1}.").format(task_code, row.status.lower()))
	row.status = "Blocked"
	row.blocked_reason = reason.strip()
	_save(doc, _("Task {0} blocked: {1}").format(row.stage_name, reason.strip()))
	return doc.status


@frappe.whitelist()
def unblock_task(installation, task_code=None, remarks=None):
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	if row.status != "Blocked":
		frappe.throw(_("Task {0} is not blocked.").format(task_code))
	row.status = "In Progress" if (row.task_document and _live(row)) else "Pending"
	row.blocked_reason = None
	if remarks:
		row.remarks = remarks
	_save(doc, _("Task {0} unblocked.").format(row.stage_name))
	return doc.status


@frappe.whitelist()
def reopen_task(installation, task_code=None, reason=None):
	"""Manager-only. Puts one task back - this one, nothing after it, because there is no after."""
	_require_manager(_("reopen a task"))
	if not task_code:
		frappe.throw(_("Which task?"))
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when reopening a task."))
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	row.status = "In Progress" if (row.task_document and _live(row)) else "Pending"
	row.actual_completion_date = None
	row.completed_by = None
	row.blocked_reason = None
	row.skip_reason = None
	row.days_in_stage = 0
	row.is_sla_breached = 0
	if row.status == "Pending":
		row.actual_start_date = None
	_save(doc, _("Task {0} reopened: {1}").format(row.stage_name, reason.strip()))
	return doc.current_stage


@frappe.whitelist()
def assign_task(installation, task_code=None, user=None, due_date=None):
	if not task_code or not user:
		frappe.throw(_("A task and a user are both needed."))
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission("write")
	row = _get_stage(doc, task_code)
	row.assigned_to = user
	row.assigned_by = frappe.session.user
	row.assigned_on = now_datetime()
	if due_date:
		row.due_date = getdate(due_date)
	_save(doc, _("Task {0} assigned to {1}.").format(row.stage_name, user))
	try:
		from frappe.desk.form.assign_to import add as assign_add

		assign_add(
			{
				"assign_to": [user],
				"doctype": "Solar Installation",
				"name": doc.name,
				"description": f"[{task_code}] {row.stage_name}",
				"date": row.due_date,
			}
		)
	except Exception:
		# The assignment is a convenience notification; the row is the record.
		frappe.clear_last_message()
	return row.assigned_to


def link_document(installation, task_code, doctype, name, status="In Progress", force=False,
                  actual_date=None, reference=None, cost=None, silent=False):
	"""Attach a document to a task row from code - the handoff for ORD, the rebuild patch.

	Refuses to steal a row from another live document unless `force`.
	"""
	doc = installation if not isinstance(installation, str) else frappe.get_doc(
		"Solar Installation", installation, for_update=True
	)
	row = _row(doc, task_code)
	if not row:
		return None
	if not force and row.task_document and row.task_document != name and _live(row):
		return None
	row.task_doctype = doctype
	row.task_document = name
	row.skip_reason = None
	if not row.actual_start_date:
		row.actual_start_date = getdate(actual_date or today())
	if reference:
		row.external_reference = reference
	if cost is not None:
		row.cost = flt(cost)
	was = row.status
	if status == "Completed":
		row.status = "Completed"
		row.actual_completion_date = getdate(actual_date or today())
		row.completed_by = frappe.session.user
		row.blocked_reason = None
	elif was in ("Pending", "Skipped"):
		row.status = "In Progress"
	_save(doc, _("Task {0} linked to {1} {2}.").format(row.stage_name, _(doctype), name))
	if status == "Completed" and was != "Completed" and not silent:
		notify_task_completed(doc, task_code)
	return row


def _live(row):
	if not (row.task_doctype and row.task_document):
		return False
	live = frappe.db.get_value(row.task_doctype, row.task_document, "docstatus")
	return live is not None and cint(live) < 2
