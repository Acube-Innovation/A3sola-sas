# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Asking for the advance (the Advance Payment task, ADV) until it comes.

Who is asked, and from when, follows who pays (Solar Installation.is_financed):
- the customer, once Form 1 is submitted (the FRM1 task completed) - on a job the customer
  pays, Form 1 starts with the order, ahead of the advance (tasks._start_form1_early);
- the bank, some days after the loan is sanctioned (Loan Application.sanctioned_on, A3 Sola
  Settings' bank_payment_followup_days, 5).

The job carries the day it is next due (advance_followup_due_on). The task's people ask from
the Advance Payment page - a message for WhatsApp, e-mail or a call, with the payment
statement's link - and log each ask (payment_followups); the next is due some days later,
or on the day they choose. On the due day each of them gets a to-do (daily_chase). It stops
when the advance is recorded in full, or confirmed.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, format_date, format_datetime, getdate, now_datetime, today

from a3_sola.api import stages, task_assignees
from a3_sola.api.settings import get_int

TASK = "ADV"
VIA = ("WhatsApp", "Email", "Call", "In Person")
#: How a follow-up to-do begins - and how it is found again to close. Not "[": My Work hides
#: those as repeats of the task itself (my_work._is_duplicate).
TODO_TEXT = "Ask for the advance payment"


def _row(inst, code=TASK):
	return next((r for r in inst.get("stages") or [] if r.stage_code == code), None)


def is_bank(inst):
	return bool(cint(inst.get("is_financed")))


def interval(inst):
	"""Days from one ask to the next: the bank's, or the customer's."""
	if is_bank(inst):
		return get_int("bank_payment_followup_days", 5) or 5
	return get_int("client_payment_followup_days", 3) or 3


def outstanding(inst):
	"""What is still to be asked for on the advance: the phase's collect, less the payments
	recorded and waiting for Accounts. None when the job has no payment terms."""
	from a3_sola.api import billing, payment_tasks

	due = billing.phase_due(inst, TASK)
	if not due:
		return None
	plan = billing.plan_of(inst)
	waiting = sum(flt(p.amount) for p in payment_tasks._payments(plan, TASK, "Awaiting Confirmation")) if plan else 0
	return max(flt(due["phase"]["collect"]) - waiting, 0)


def is_open(inst):
	"""Whether the advance is still to be asked for."""
	row = _row(inst)
	if not row or row.status in ("Completed", "Skipped"):
		return False
	left = outstanding(inst)
	return left is None or left >= 0.5


def _loan(inst):
	if not inst.get("loan_application"):
		return frappe._dict()
	return frappe.db.get_value("Loan Application", inst.loan_application, ["name", "status", "lender", "lender_branch",
		"relationship_manager", "contact_number", "loan_sanction_no", "sanctioned_on"], as_dict=True) or frappe._dict()


# ------------------------------------------------------------------ when it falls due
def on_form1_completed(installation, task_code):
	"""Form 1 is submitted: on a job the customer pays, the customer is asked for the advance
	from today (tasks.AFTER_COMPLETE)."""
	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	if is_bank(inst) or inst.get("advance_followup_due_on") or not is_open(inst):
		return
	inst.db_set("advance_followup_due_on", today(), update_modified=False)


def on_loan_sanctioned(loan):
	"""The loan is sanctioned: the bank is asked for the advance some days later - until the
	first ask, the day follows the sanction date if it is corrected (LoanApplication.push_to_installation)."""
	if not (loan.get("sanctioned_on") and loan.get("solar_installation")):
		return
	inst = frappe.get_doc("Solar Installation", loan.solar_installation)
	if not is_bank(inst) or not is_open(inst) or any(r.task_code == TASK for r in inst.get("payment_followups") or []):
		return
	due = add_days(getdate(loan.sanctioned_on), interval(inst))
	if inst.get("advance_followup_due_on") != due:
		inst.db_set("advance_followup_due_on", due, update_modified=False)


def started(inst):
	"""Whether asking has begun for this job: Form 1 submitted on a job the customer pays, the
	loan sanctioned on a bank-loan job."""
	if is_bank(inst):
		return bool(_loan(inst).get("sanctioned_on"))
	form1 = _row(inst, "FRM1")
	return bool(form1 and form1.status == "Completed")


def first_due(inst):
	"""The day the first ask falls due: the sanction date plus the interval for the bank, the
	day Form 1 was completed for the customer."""
	if is_bank(inst):
		return getdate(add_days(_loan(inst).sanctioned_on, interval(inst)))
	form1 = _row(inst, "FRM1")
	return getdate(form1.actual_completion_date or today())


def after_payment(inst):
	"""A payment recorded or confirmed: nothing more to ask once the advance is covered. On
	the caller's copy; it saves."""
	if inst.get("advance_followup_due_on") and not is_open(inst):
		inst.advance_followup_due_on = None
		_close_todos(inst)


def after_send_back(inst):
	"""A payment Accounts did not find: the advance is owed again, and asked for from today. On
	the caller's copy; it saves."""
	if not inst.get("advance_followup_due_on") and started(inst) and is_open(inst):
		inst.advance_followup_due_on = today()


# ------------------------------------------------------------------ the page
def _payer(inst):
	"""Who is asked, and how to reach them."""
	if is_bank(inst):
		loan = _loan(inst)
		lender = loan.lender or inst.get("lender") or ""
		branch = loan.lender_branch or inst.get("lender_branch") or ""
		return {"payer": "Bank", "name": ", ".join(x for x in (lender, branch) if x) or _("The bank"),
			"person": loan.relationship_manager or "", "mobile": loan.contact_number or "", "email": "",
			"loan": loan.name or "", "loan_status": loan.status or "", "sanction_no": loan.loan_sanction_no or inst.get("loan_sanction_no") or "",
			"sanctioned_on": format_date(loan.sanctioned_on, "d MMM yyyy") if loan.sanctioned_on else ""}
	return {"payer": "Client", "name": inst.get("consumer_name") or inst.get("lead_name") or "", "person": "",
		"mobile": inst.get("consumer_mobile") or inst.get("lead_mobile") or "", "email": inst.get("consumer_email") or ""}


def _waiting(inst, payer):
	"""Why nobody is asked yet."""
	if payer["payer"] == "Bank":
		if not payer.get("loan"):
			return _("The bank is asked {0} days after the loan is sanctioned. This project has no loan application yet.").format(interval(inst))
		return _("The bank is asked {0} days after the loan is sanctioned. Loan application {1} is {2}.").format(
			interval(inst), payer["loan"], (payer.get("loan_status") or _("not sanctioned")).lower())
	form1 = _row(inst, "FRM1")
	return _("The customer is asked once Form 1 is submitted. Form 1 is {0}.").format(
		(form1.status if form1 else _("not on this project")).lower())


def state(inst, task_code):
	"""What the Advance Payment page shows of the asking: who, when next, and every ask so far."""
	if task_code != TASK:
		return None
	payer = _payer(inst)
	open_ = is_open(inst)
	due = inst.get("advance_followup_due_on")
	asks = [{
		"on": format_datetime(r.asked_on, "d MMM yyyy, h:mm a") if r.asked_on else "",
		"by": frappe.db.get_value("User", r.asked_by, "full_name") or r.asked_by or "",
		"payer": r.payer, "via": r.via, "contact": r.contact or "", "note": r.note or "",
		"next": format_date(r.next_followup_on, "d MMM yyyy") if r.next_followup_on else "",
	} for r in sorted((r for r in inst.get("payment_followups") or [] if r.task_code == TASK),
		key=lambda r: str(r.asked_on or ""), reverse=True)]
	return {
		"open": open_, **payer,
		"due_on": format_date(due, "d MMM yyyy") if due and open_ else "",
		"overdue": bool(due and open_ and getdate(due) < getdate(today())),
		"due_today": bool(due and open_ and getdate(due) == getdate(today())),
		"waiting": _waiting(inst, payer) if open_ and not due else "",
		"interval": interval(inst),
		"next_default": str(add_days(today(), interval(inst))),
		"asks": asks,
		# Staff who may edit the job, or the task's own people - a dealer owning the lead.
		"can_ask": open_ and bool(inst.has_permission("write") or task_assignees.holds(inst, task_code)),
	}


#: The messages, in WhatsApp's *bold*. Signed as the person asking (portal_share.SIGNATURE).
CLIENT_MESSAGE = """Dear {name},

Greetings from Renewcore Innovations. Thank you for choosing us for your rooftop solar project ({job}).

The advance payment of *{amount}* is now due. Your payment statement is at the link below; kindly make the payment and share the transaction reference with us.

{statement}

"""
BANK_MESSAGE = """Dear Sir/Madam,

Sub: Rooftop solar loan of {customer}{sanction}

The advance disbursement of *{amount}* for this rooftop solar project ({job}) is awaited. Kindly release it at the earliest. The payment statement is at the link below.

{statement}

"""


def _statement_link(inst):
	"""A link that opens the payment statement, signed and sealed, without a login - or ""
	when the task does not list it."""
	from a3_sola.api import payment_statement_print, task_share

	try:
		return task_share.share_link(inst.name, TASK, payment_statement_print.url(inst.name) + "&signed=1")["link"]
	except frappe.PermissionError:
		frappe.clear_last_message()
		return ""


@frappe.whitelist(methods=["POST"])
def ask_message(installation, task_code=TASK):
	"""The message asking for the advance - to the customer or to the bank - with the payment
	statement's link, and the WhatsApp link to send it with."""
	from a3_sola.api import outreach, payment_tasks
	from a3_sola.api.portal_share import SIGNATURE, _sender

	inst = payment_tasks._job(installation, "read", task_code)
	payer = _payer(inst)
	left = outstanding(inst)
	amount = frappe.utils.fmt_money(left, currency="INR") if left else _("the advance")
	statement = _statement_link(inst)
	customer = inst.get("consumer_name") or inst.get("lead_name") or inst.name
	if payer["payer"] == "Bank":
		sanction = "".join(x for x in (
			_(", sanction no. {0}").format(payer["sanction_no"]) if payer.get("sanction_no") else "",
			_(" dated {0}").format(payer["sanctioned_on"]) if payer.get("sanctioned_on") else ""))
		text = BANK_MESSAGE.format(customer=customer, sanction=sanction, amount=amount, job=inst.name, statement=statement)
		subject = _("Advance disbursement - {0} ({1})").format(customer, inst.name)
	else:
		text = CLIENT_MESSAGE.format(name=payer["name"] or _("Sir/Madam"), amount=amount, job=inst.name, statement=statement)
		subject = _("Advance payment - {0}").format(inst.name)
	sender, phone = _sender()
	text = text.replace("\n\n\n", "\n\n") + SIGNATURE.format(sender=sender, phone=phone)
	return {"message": text, "subject": subject, "mobile": payer["mobile"], "email": payer["email"],
		"whatsapp": outreach.whatsapp_link(payer["mobile"], text) if payer["mobile"] else "",
		"statement": statement}


@frappe.whitelist(methods=["POST"])
def log_ask(installation, via, note=None, next_on=None, contact=None, task_code=TASK):
	"""The advance was asked for: logged on the job, and the next ask due `next_on` - by
	default the interval from today. Any follow-up to-do of the job is done."""
	from a3_sola.api import payment_tasks

	if via not in VIA:
		frappe.throw(_("Say how the payment was asked for: {0}.").format(", ".join(VIA)))
	inst = payment_tasks._job(installation, "write", task_code)
	if not (inst.has_permission("write") or task_assignees.holds(inst, task_code)):
		frappe.throw(_("Only the task's people or those who keep the project can log an ask."), frappe.PermissionError)
	if not is_open(inst):
		frappe.throw(_("There is nothing left to ask for on the advance."), title=_("Advance Covered"))
	next_on = getdate(next_on) if next_on else getdate(add_days(today(), interval(inst)))
	if next_on < getdate(today()):
		frappe.throw(_("The next follow-up cannot be in the past."), title=_("Next Follow-up"))
	payer = _payer(inst)
	contact = (contact or "").strip() or ", ".join(x for x in (payer.get("person"), payer.get("mobile"), payer.get("email")) if x)
	inst.append("payment_followups", {
		"task_code": TASK, "asked_on": now_datetime(), "asked_by": frappe.session.user, "payer": payer["payer"],
		"via": via, "contact": contact[:140] or None, "note": (note or "").strip() or None, "next_followup_on": next_on,
	})
	inst.advance_followup_due_on = next_on
	_close_todos(inst)
	who = _("the bank") if payer["payer"] == "Bank" else _("the customer")
	stages._save(inst, _("Advance Payment: {0} asked {1} for the payment by {2}{3}; next follow-up {4}.").format(
		frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user, who, via,
		" - " + note.strip() if (note or "").strip() else "", format_date(next_on, "d MMM yyyy")))
	return payment_tasks.state(installation, TASK)


# ------------------------------------------------------------------ reminders
def _todos(inst, status="Open"):
	return frappe.get_all("ToDo", filters={"reference_type": "Solar Installation", "reference_name": inst.name,
		"status": status, "description": ["like", f"{TODO_TEXT}%"]}, fields=["name", "allocated_to", "date"])


def _close_todos(inst):
	for todo in _todos(inst):
		frappe.db.set_value("ToDo", todo.name, "status", "Closed", update_modified=False)


def daily_chase():
	"""Each job whose advance is due to be asked for today, or was due and not asked: a to-do
	for each of the task's people, once per due day."""
	from a3_sola.api import task_assignees

	raised = 0
	for name in frappe.get_all("Solar Installation", filters={"docstatus": 1,
			"advance_followup_due_on": ["<=", today()]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		if not is_open(inst):
			inst.db_set("advance_followup_due_on", None, update_modified=False)
			_close_todos(inst)
			continue
		due = getdate(inst.advance_followup_due_on)
		have = {(t.allocated_to, getdate(t.date) if t.date else None) for t in _todos(inst)}
		payer = _payer(inst)
		left = outstanding(inst)
		text = _("{0} of {1}: {2} ({3}) - ask {4}{5}.").format(
			TODO_TEXT, frappe.utils.fmt_money(left, currency="INR") if left else _("the advance"),
			inst.get("consumer_name") or inst.get("lead_name") or inst.name, inst.name,
			_("the bank, {0}").format(payer["name"]) if payer["payer"] == "Bank" else _("the customer"),
			_(", due since {0}").format(format_date(due, "d MMM")) if due < getdate(today()) else "")
		for user in task_assignees.people(inst, TASK):
			if (user, due) in have:
				continue
			frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "date": due, "priority": "High",
				"description": text, "reference_type": "Solar Installation", "reference_name": inst.name,
			}).insert(ignore_permissions=True)
			raised += 1
	frappe.logger("a3_sola").info({"event": "payment_followup.daily_chase", "raised": raised})
	return raised
