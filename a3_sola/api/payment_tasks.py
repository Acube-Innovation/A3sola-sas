# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A payment task: confirmed, not carried out in a document.

Nothing is filled in for the advance but the payment itself. Whoever takes it says whether it
has come - how much, into which bank, received by which firm (Renewcore or RIM Projects) - and
files the receipt or bank advice; the task then goes to Accounts - assigned to them, and they are told -
and is done when an accounts person confirms the money is in. Sent back, it waits for the
payment again, with the reason, and goes back to the person who marked it.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, format_date, format_datetime, getdate, now_datetime, today

from a3_sola.api import stages, task_assignees
from a3_sola.api.stages import _get_stage

#: Payment tasks, and the one document each asks for (its register row).
PAYMENT_TASKS = {
	"ADV": "Advance receipt or bank advice",
	"BAL": "Balance receipt or bank advice",
	"PCOM": "Commissioning payment receipt or bank advice",
}
#: Why a payment task is skipped on a job whose terms have no such phase - and the mark that
#: it was skipped by the terms, not by hand.
NOT_IN_TERMS = "Not in this job's payment terms"
#: Who may confirm a payment: Accounts, and the managers who stand in for them.
CONFIRMER_ROLES = {task_assignees.ACCOUNTS_ROLE, "Accounts Manager", "Accounts User", "System Manager"}
AWAITING = "Awaiting Accounts"


def firms(company):
	"""{firm: account} a payment to this company's jobs can be received by - the receiving
	firms of its Solar Company Account Mapping (Renewcore, RIM Projects), each with its ledger."""
	from a3_sola.solar_projects.doctype.solar_company_account_mapping.solar_company_account_mapping import (
		receiving_firms,
	)

	return receiving_firms(company)


def is_payment_task(code):
	return code in PAYMENT_TASKS


def can_confirm():
	return bool(CONFIRMER_ROLES & set(frappe.get_roles()))


def _job(installation, ptype):
	doc = frappe.get_doc("Solar Installation", installation, for_update=True)
	doc.check_permission(ptype)
	return doc


def _row(inst, code):
	if not is_payment_task(code):
		frappe.throw(_("{0} is not a payment task.").format(code), frappe.ValidationError)
	return _get_stage(inst, code)


def _receipt(inst, code):
	"""The task's document row on the job's register, or None on a job whose checklist has
	none - the page's upload then makes it, by name (portal_tasks.upload)."""
	name = PAYMENT_TASKS[code]
	row = next((d for d in inst.documents if d.stage_code == code and d.document_name == name), None)
	return row


def awaiting(row):
	"""Marked received and waiting for Accounts."""
	return bool(row.get("payment_received_by")) and row.status not in ("Completed", "Skipped")


def _full_name(user):
	return frappe.db.get_value("User", user, "full_name") or user if user else ""


def _notify(inst, users, subject):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	users = [u for u in users if u and u != frappe.session.user]
	if users:
		enqueue_create_notification(users, {
			"type": "Alert", "subject": subject, "document_type": "Solar Installation",
			"document_name": inst.name, "from_user": frappe.session.user,
		})


def _due(inst, task_code):
	"""This payment's phase of the job's payment terms - its share, the arrears carried in from
	the phases before, what to collect now - and the whole schedule; None without terms."""
	from a3_sola.api import billing

	due = billing.phase_due(inst, task_code)
	if not due:
		return None
	money = lambda v: fmt_money(v, currency="INR")  # noqa: E731
	phase = due["phase"]
	return {
		"code": task_code, "name": phase["name"], "percent": phase["percent"], "terms": due["terms"],
		"amount": phase["amount"], "amount_text": money(phase["amount"]),
		"arrears": phase["arrears"], "arrears_text": money(phase["arrears"]),
		"credit": phase["credit"], "credit_text": money(phase["credit"]),
		"collect": phase["collect"], "collect_text": money(phase["collect"]),
		"base": due["base"], "base_text": money(due["base"]),
		"received_total_text": money(due["received"]), "remaining_total": due["remaining"],
		"remaining_total_text": money(due["remaining"]),
		"schedule": [{**p, "current": p["code"] == task_code, "amount_text": money(p["amount"]),
			"received_text": money(p["received"]) if p["received"] else "",
			"remaining_text": money(p["remaining"])} for p in due["phases"]],
	}


def apply_phases(inst):
	"""Skip a payment task whose phase the job's terms do not have (the third payment on 70:30
	terms), and bring it back if the terms change. Rows only; the caller saves. Returns
	whether anything changed."""
	from a3_sola.api import billing

	schedule = billing.payment_phases(inst)
	if not schedule:
		return False
	present = {p["code"] for p in schedule["phases"]}
	changed = False
	for row in inst.get("stages") or []:
		if row.stage_code not in PAYMENT_TASKS:
			continue
		if row.stage_code not in present and row.status == "Pending":
			row.status, row.skip_reason = "Skipped", NOT_IN_TERMS
			changed = True
		elif row.stage_code in present and row.status == "Skipped" and row.skip_reason == NOT_IN_TERMS:
			row.status, row.skip_reason = "Pending", None
			changed = True
	return changed


@frappe.whitelist()
def state(installation, task_code):
	"""What the payment page shows: where the task stands, its receipt, and what this user may do."""
	inst = _job(installation, "read")
	row = _row(inst, task_code)
	receipt = _receipt(inst, task_code)
	return {
		"task": {"code": row.stage_code, "name": row.stage_name, "status": AWAITING if awaiting(row) else row.status},
		"document": {"row": receipt.name if receipt else None, "name": PAYMENT_TASKS[task_code],
			"file_url": receipt.attachment if receipt else None},
		"received_by": _full_name(row.payment_received_by),
		"received_on": format_datetime(row.payment_received_on, "d MMM yyyy, h:mm a") if row.payment_received_on else "",
		"payment": {"amount": flt(row.get("payment_amount")), "amount_text": fmt_money(row.get("payment_amount"), currency="INR") if flt(row.get("payment_amount")) else "",
			"bank": row.get("payment_bank") or "", "company": row.get("payment_company") or "",
			"account": row.get("payment_account") or ""},
		"company_options": list(firms(inst.company)),
		"due": _due(inst, task_code),
		"confirmed_by": _full_name(row.completed_by) if row.status == "Completed" else "",
		"confirmed_on": str(row.actual_completion_date or "") if row.status == "Completed" else "",
		"remarks": row.remarks or "",
		"can_mark": bool(inst.has_permission("write")) and row.status not in ("Completed", "Skipped"),
		"can_confirm": can_confirm() and awaiting(row),
		**_phase_payments(inst, task_code),
	}


def _phase_payments(inst, task_code):
	"""The phase's payments on the job's schedule (newest first) and where it stands."""
	from a3_sola.api import billing

	plan = billing.plan_of(inst)
	if not plan:
		return {"payments": [], "payment_status": "", "pending_text": ""}
	status, pending = billing.phase_standing(plan, task_code)
	money = lambda v: fmt_money(flt(v), currency="INR")  # noqa: E731
	return {
		"payments": [{
			"row": p.name, "amount_text": money(p.amount),
			"date": format_date(p.payment_date, "d MMM yyyy") if p.payment_date else "",
			"mode": p.payment_mode or "", "reference": p.reference_no or "", "bank": p.bank or "",
			"firm": p.receiving_firm or "", "status": p.status, "receipt": p.receipt or "", "remarks": p.remarks or "",
		} for p in sorted(_payments(plan, task_code), key=lambda p: (str(p.payment_date or ""), p.idx), reverse=True)],
		"payment_status": status, "pending_text": money(pending) if status else "",
		"modes": list(billing.PAYMENT_MODES),
	}


def _plan(inst):
	"""The job's billing plan, where its payments are kept - made now if the job has none yet
	- or None when it cannot have one (no customer or contract value): its payment task then
	keeps the one payment on its row, as before the schedule."""
	from a3_sola.api import billing

	plan = billing.plan_of(inst)
	if not plan:
		name = billing.ensure_plan_for_installation(inst.name, replay=False)
		plan = frappe.get_doc("Solar Billing Plan", name) if name else None
	return plan


def _save_plan(plan):
	plan.flags.ignore_validate_update_after_submit = True
	plan.flags.ignore_permissions = True
	plan.save(ignore_permissions=True)


def _payments(plan, code, status=None, row=None):
	return [p for p in plan.get("payments") or [] if p.phase_code == code and (not status or p.status == status)
		and (not row or p.name == row)]


def _new_receipt(inst, code, plan):
	"""The receipt for a payment being recorded: one posted with it, filed in the job's
	register (the task's receipt row while it is empty, else a numbered one beside it) - or the
	receipt already uploaded to the task that no payment has used yet."""
	from a3_sola.api import documents, portal_tasks

	used = {p.receipt for p in plan.get("payments") or [] if p.receipt}
	file_url = portal_tasks.posted_file(inst, PAYMENT_TASKS[code])
	if file_url:
		name, row = PAYMENT_TASKS[code], _receipt(inst, code)
		if row and row.attachment:
			taken = sum(1 for d in inst.documents if d.stage_code == code and (d.document_name or "").startswith(name))
			name = "{0} ({1})".format(name, taken + 1)
		documents.register_document(inst, code, "Solar Installation", inst.name, name, file_url, kind="Uploaded", save=False)
		return file_url
	row = _receipt(inst, code)
	if row and row.attachment and row.attachment not in used:
		return row.attachment
	frappe.throw(_("Upload the {0} for this payment.").format(PAYMENT_TASKS[code].lower()), title=_("Receipt Needed"))


@frappe.whitelist(methods=["POST"])
def mark_received(installation, task_code, amount=None, bank=None, company=None, payment_date=None, mode=None,
		reference=None):
	"""A payment has come - `amount` on `payment_date`, by `mode` (with its `reference`), into
	`bank`, received by `company` (one of the firms) - with its receipt (posted with it, or
	already uploaded to the task). It goes on the job's payment schedule awaiting Accounts, and
	the task to Accounts to confirm. A phase can be paid in parts: each is recorded the same way."""
	amount, bank, company = flt(amount), (bank or "").strip(), (company or "").strip()
	payment_date = getdate(payment_date) if payment_date else getdate(today())
	if payment_date > getdate(today()):
		frappe.throw(_("The payment date cannot be in the future."), title=_("Payment Date"))
	from a3_sola.api.billing import PAYMENT_MODES

	if mode and mode not in PAYMENT_MODES:
		frappe.throw(_("{0} is not a payment mode.").format(mode), frappe.ValidationError)
	missing = [label for label, value in ((_("the amount received"), amount > 0), (_("the bank"), bank),
		(_("the company that received it"), company)) if not value]
	if missing:
		frappe.throw(_("Enter {0}.").format(", ".join(missing)), title=_("Payment Details Needed"))
	inst = _job(installation, "write")
	accounts = firms(inst.company)
	if not accounts:
		frappe.throw(_("No receiving firms are set up for {0}. Add them, each with its account, under Payment "
			"Receiving Firms in Solar Company Account Mapping.").format(inst.company), title=_("Firms Not Set Up"))
	if company not in accounts:
		frappe.throw(_("{0} is not one of {1}.").format(company, ", ".join(accounts)), frappe.ValidationError)
	row = _row(inst, task_code)
	if row.status in ("Completed", "Skipped"):
		frappe.throw(_("{0} is already {1}.").format(row.stage_name, row.status.lower()))
	plan = _plan(inst)
	if plan:
		receipt = _new_receipt(inst, task_code, plan)
		plan.append("payments", {
			"phase_code": task_code, "amount": amount, "payment_date": payment_date, "payment_mode": mode or None,
			"reference_no": (reference or "").strip() or None, "bank": bank, "receiving_firm": company,
			"account": accounts[company], "receipt": receipt, "status": "Awaiting Confirmation",
			"recorded_by": frappe.session.user, "recorded_on": now_datetime(),
		})
		_save_plan(plan)
	elif not ((_receipt(inst, task_code) or frappe._dict()).attachment):
		frappe.throw(_("Upload the {0} first.").format(PAYMENT_TASKS[task_code].lower()), title=_("Receipt Needed"))
	# The task's row shows the latest payment (and so that it awaits Accounts).
	row.payment_received_by = frappe.session.user
	row.payment_received_on = now_datetime()
	row.payment_amount, row.payment_bank, row.payment_company = amount, bank, company
	row.payment_account = accounts[company]
	# The first advance, whatever its share, starts the work it pays for (stages.start_on_advance).
	started = stages.start_on_advance(inst) if task_code == "ADV" and row.status == "Pending" else []
	row.status = "In Progress"
	row.actual_start_date = row.actual_start_date or today()
	accounts = task_assignees.resolve(inst, task_assignees.ACCOUNTS)
	if accounts:
		task_assignees.put(inst, task_code, accounts)
	due = _due(inst, task_code)
	share = ""
	if due:
		share = _(" (to collect {0}: this phase {1}% - {2}{3})").format(due["collect_text"], flt(due["percent"], 1),
			due["amount_text"], _(" + arrears {0}").format(due["arrears_text"]) if due["arrears"] else "")
	stages._save(inst, _("{0}: {1} received in {2} by {3}{4}, marked by {5}; sent to Accounts to confirm.").format(
		row.stage_name, fmt_money(amount, currency="INR"), bank, company, share, _full_name(frappe.session.user)))
	if started:
		stages.notify_started(inst, started)
		inst.add_comment("Comment", _("Advance received: started {0}.").format(", ".join(r.stage_name for r in started)))
	_notify(inst, accounts, _("{0} of {1} received on {2} - please confirm").format(
		row.stage_name, fmt_money(amount, currency="INR"), inst.name))
	return state(installation, task_code)


def _awaiting_payments(inst, row, task_code, payment):
	"""The phase's payments awaiting Accounts - the one `payment`, else all of them. A task
	marked before the plan held payments has none: its row's amount is moved onto the plan
	first, so it is confirmed like any other."""
	plan = _plan(inst)
	if not plan:
		if not awaiting(row):
			frappe.throw(_("{0} is not waiting for confirmation.").format(row.stage_name))
		return None, []
	if not _payments(plan, task_code) and awaiting(row) and flt(row.get("payment_amount")):
		receipt = _receipt(inst, task_code)
		plan.append("payments", {
			"phase_code": task_code, "amount": flt(row.payment_amount),
			"payment_date": getdate(row.payment_received_on) if row.payment_received_on else getdate(today()),
			"bank": row.payment_bank, "receiving_firm": row.payment_company, "account": row.payment_account,
			"receipt": receipt.attachment if receipt else None, "status": "Awaiting Confirmation",
			"recorded_by": row.payment_received_by, "recorded_on": row.payment_received_on,
		})
	waiting = _payments(plan, task_code, "Awaiting Confirmation", payment)
	if not waiting:
		frappe.throw(_("{0} has no payment waiting for confirmation.").format(row.stage_name))
	return plan, waiting


def _after_review(inst, row, plan, task_code):
	"""The task once Accounts has looked: still awaiting while a payment of its waits; else
	it is no longer with Accounts."""
	if _payments(plan, task_code, "Awaiting Confirmation"):
		return
	row.payment_received_by = None
	row.payment_received_on = None


@frappe.whitelist(methods=["POST"])
def confirm(installation, task_code, payment=None):
	"""Accounts confirms the money is in - the one `payment`, else every payment of the phase
	waiting. It counts on the schedule from now; the task is done when the phase is paid in
	full, and otherwise stays open (Partly Paid) for the rest."""
	from a3_sola.api import billing

	if not can_confirm():
		frappe.throw(_("Only Accounts can confirm a payment."), frappe.PermissionError)
	# Accounts reads the job; the task's own transition is the engine's to save.
	inst = _job(installation, "read")
	row = _row(inst, task_code)
	plan, waiting = _awaiting_payments(inst, row, task_code, payment)
	if plan:
		for p in waiting:
			p.status, p.confirmed_by, p.confirmed_on = "Confirmed", frappe.session.user, now_datetime()
		_save_plan(plan)
		recorders = list({p.recorded_by for p in waiting if p.recorded_by})
		amount = fmt_money(sum(flt(p.amount) for p in waiting), currency="INR")
		status, pending = billing.phase_standing(plan, task_code)
		_after_review(inst, row, plan, task_code)
	else:
		# No schedule to keep it on: the payment on the task's row is the phase, done.
		recorders, status, pending = [row.payment_received_by], "Paid", 0.0
		amount = fmt_money(row.get("payment_amount"), currency="INR")
	if status == "Paid":
		row.status = "Completed"
		row.actual_completion_date = today()
		row.completed_by = frappe.session.user
		row.blocked_reason = None
		stages._save(inst, _("{0}: {1} confirmed by {2} - paid in full.").format(
			row.stage_name, amount, _full_name(frappe.session.user)))
		from a3_sola.api.tasks import notify_task_completed

		notify_task_completed(inst, task_code)
	else:
		row.status = "In Progress"
		stages._save(inst, _("{0}: {1} confirmed by {2} - {3} still pending.").format(
			row.stage_name, amount, _full_name(frappe.session.user), fmt_money(pending, currency="INR")))
	_notify(inst, recorders, _("{0} of {1} on {2} confirmed by Accounts").format(row.stage_name, amount, inst.name))
	return state(installation, task_code)


@frappe.whitelist(methods=["POST"])
def send_back(installation, task_code, reason=None, payment=None):
	"""Accounts has not found the money - the one `payment`, else every payment of the phase
	waiting: it does not count, it says why, and the task goes back to whoever recorded it."""
	if not can_confirm():
		frappe.throw(_("Only Accounts can send a payment back."), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Say why the payment is not confirmed."))
	inst = _job(installation, "read")
	row = _row(inst, task_code)
	plan, waiting = _awaiting_payments(inst, row, task_code, payment)
	for p in waiting:
		p.status, p.remarks = "Sent Back", _("Not confirmed by Accounts: {0}").format(reason)
	marked_by = next((p.recorded_by for p in waiting if p.recorded_by), None) or row.payment_received_by
	if plan:
		_save_plan(plan)
		_after_review(inst, row, plan, task_code)
	else:
		row.payment_received_by = row.payment_received_on = None
	# The row's amount, bank and company stay, for the person to correct rather than retype.
	if not awaiting(row):
		row.status = "In Progress" if plan and _payments(plan, task_code, "Confirmed") else "Pending"
	row.remarks = _("Not confirmed by Accounts: {0}").format(reason)
	if marked_by:
		task_assignees.put(inst, task_code, [marked_by])
	stages._save(inst, _("{0}: sent back by {1} - {2}").format(row.stage_name, _full_name(frappe.session.user), reason))
	_notify(inst, [marked_by], _("{0} on {1} not confirmed: {2}").format(row.stage_name, inst.name, reason))
	return state(installation, task_code)
