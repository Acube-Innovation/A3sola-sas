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
from frappe.utils import flt, fmt_money, format_datetime, now_datetime, today

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
	}


@frappe.whitelist(methods=["POST"])
def mark_received(installation, task_code, amount=None, bank=None, company=None):
	"""The payment has come - `amount`, into `bank`, received by `company` (one of the firms) -
	and with its receipt filed, the task goes to Accounts to confirm."""
	amount, bank, company = flt(amount), (bank or "").strip(), (company or "").strip()
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
	receipt = _receipt(inst, task_code)
	if not (receipt and receipt.attachment):
		frappe.throw(_("Upload the {0} first.").format(PAYMENT_TASKS[task_code].lower()), title=_("Receipt Needed"))
	row.payment_received_by = frappe.session.user
	row.payment_received_on = now_datetime()
	row.payment_amount, row.payment_bank, row.payment_company = amount, bank, company
	row.payment_account = accounts[company]
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
	_notify(inst, accounts, _("{0} of {1} received on {2} - please confirm").format(
		row.stage_name, fmt_money(amount, currency="INR"), inst.name))
	return state(installation, task_code)


@frappe.whitelist(methods=["POST"])
def confirm(installation, task_code):
	"""Accounts confirms the money is in: the task is done."""
	if not can_confirm():
		frappe.throw(_("Only Accounts can confirm a payment."), frappe.PermissionError)
	# Accounts reads the job; the task's own transition is the engine's to save.
	inst = _job(installation, "read")
	row = _row(inst, task_code)
	if not awaiting(row):
		frappe.throw(_("{0} is not waiting for confirmation.").format(row.stage_name))
	row.status = "Completed"
	row.actual_completion_date = today()
	row.completed_by = frappe.session.user
	row.blocked_reason = None
	stages._save(inst, _("{0}: payment confirmed by {1}.").format(row.stage_name, _full_name(frappe.session.user)))
	from a3_sola.api.tasks import notify_task_completed

	notify_task_completed(inst, task_code)
	_notify(inst, [row.payment_received_by], _("{0} on {1} confirmed by Accounts").format(row.stage_name, inst.name))
	return state(installation, task_code)


@frappe.whitelist(methods=["POST"])
def send_back(installation, task_code, reason=None):
	"""Accounts has not found the money: the task waits for the payment again, with the reason,
	back with the person who marked it."""
	if not can_confirm():
		frappe.throw(_("Only Accounts can send a payment back."), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Say why the payment is not confirmed."))
	inst = _job(installation, "read")
	row = _row(inst, task_code)
	if not awaiting(row):
		frappe.throw(_("{0} is not waiting for confirmation.").format(row.stage_name))
	marked_by = row.payment_received_by
	row.payment_received_by = None
	row.payment_received_on = None
	# The amount, bank and company stay, for the person to correct rather than retype.
	row.status = "Pending"
	row.remarks = _("Not confirmed by Accounts: {0}").format(reason)
	if marked_by:
		task_assignees.put(inst, task_code, [marked_by])
	stages._save(inst, _("{0}: sent back by {1} - {2}").format(row.stage_name, _full_name(frappe.session.user), reason))
	_notify(inst, [marked_by], _("{0} on {1} not confirmed: {2}").format(row.stage_name, inst.name, reason))
	return state(installation, task_code)
