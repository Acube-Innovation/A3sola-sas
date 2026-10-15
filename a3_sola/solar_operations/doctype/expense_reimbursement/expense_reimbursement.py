# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Money a team member paid out of pocket for a job's task - the stamp paper, a courier,
a fee at the counter - claimed back.

The person on the task raises it (Pending Approval); an operations manager approves or
rejects it; Accounts pays it and says how (Paid). Each step is its own whitelisted call,
held to the role that takes it; what was claimed is fixed once a manager has decided on
it, so the amount approved is the amount paid. Nothing is posted to the books here - the
payment is recorded as Accounts made it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt, getdate, now_datetime, today

from a3_sola.api.stages import MANAGER_ROLES, _get_stage

#: Who pays a claim once it is approved.
ACCOUNTS_ROLES = ("Accounts Manager", "Solar Accounts Executive", "System Manager")
#: What was claimed - fixed once a manager has approved or rejected it.
CLAIM_FIELDS = (
	"claimant", "expense_date", "description", "amount", "receipt", "solar_installation",
	"task_code", "source_doctype", "source_document",
)
PAYMENT_MODES = ("Cash", "Bank Transfer", "UPI", "Cheque")


class ExpenseReimbursement(Document):
	def autoname(self):
		self.name = make_autoname("SOL-REIMB-.YYYY.-.#####", doc=self)

	def validate(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Enter the amount paid."), frappe.ValidationError)
		if self.expense_date and getdate(self.expense_date) > getdate(today()):
			frappe.throw(_("An expense cannot be paid on a future date."), frappe.ValidationError)
		inst = frappe.get_doc("Solar Installation", self.solar_installation)
		self.company = inst.company
		if self.task_code:
			self.task_name = _get_stage(inst, self.task_code).stage_name
		if self.is_new():
			self.status = "Pending Approval"
		elif not self.flags.status_change:
			self.guard_decided()

	def guard_decided(self):
		"""Once decided, the claim stands as it was decided on: a change is a new claim."""
		before = self.get_doc_before_save()
		if not before:
			return
		if self.status != before.status:
			frappe.throw(_("The status changes by approving, rejecting or paying the claim."), frappe.ValidationError)
		if before.status == "Pending Approval":
			return
		changed = [self.meta.get_label(f) for f in CLAIM_FIELDS if str(self.get(f) or "") != str(before.get(f) or "")]
		if changed:
			frappe.throw(
				_("Reimbursement {0} is {1}; {2} can no longer be changed.").format(self.name, before.status, ", ".join(changed)),
				frappe.ValidationError,
			)

	def move(self, status, note, **values):
		"""Take the claim to `status`, recording who and when, on the claim and on its job."""
		self.update(values)
		self.status = status
		self.flags.status_change = True
		self.save(ignore_permissions=True)
		self.add_comment("Info", note)
		frappe.get_doc("Solar Installation", self.solar_installation).add_comment(
			"Info", _("Reimbursement {0} ({1}, {2}): {3}").format(
				self.name, self.claimant_name or self.claimant, frappe.utils.fmt_money(self.amount, currency="INR"), note
			)
		)


def _load(name, expected):
	doc = frappe.get_doc("Expense Reimbursement", name)
	doc.check_permission("read")
	if doc.status != expected:
		frappe.throw(_("Reimbursement {0} is {1}, not {2}.").format(name, doc.status, expected), frappe.ValidationError)
	return doc


def _require(roles, action):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Only {0} can {1}.").format(" / ".join(r for r in roles if r != "System Manager"), action),
			frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def approve(name, remarks=None):
	"""A manager accepts the claim; it goes to Accounts to pay."""
	_require(MANAGER_ROLES, _("approve a reimbursement"))
	doc = _load(name, "Pending Approval")
	doc.move("Approved", _("Approved") + (f": {remarks.strip()}" if (remarks or "").strip() else ""),
		approved_by=frappe.session.user, approved_on=now_datetime(), approval_remarks=(remarks or "").strip() or None)
	return doc.status


@frappe.whitelist(methods=["POST"])
def reject(name, reason=None):
	"""A manager turns the claim down, saying why."""
	_require(MANAGER_ROLES, _("reject a reimbursement"))
	if not (reason or "").strip():
		frappe.throw(_("Say why the claim is rejected."), frappe.ValidationError)
	doc = _load(name, "Pending Approval")
	doc.move("Rejected", _("Rejected: {0}").format(reason.strip()),
		approved_by=frappe.session.user, approved_on=now_datetime(), approval_remarks=reason.strip())
	return doc.status


@frappe.whitelist(methods=["POST"])
def mark_paid(name, paid_on=None, payment_mode=None, payment_reference=None):
	"""Accounts has paid the claimant back: when, how, and the reference."""
	_require(ACCOUNTS_ROLES, _("mark a reimbursement paid"))
	if payment_mode not in PAYMENT_MODES:
		frappe.throw(_("Choose how it was paid."), frappe.ValidationError)
	paid_on = paid_on or today()
	if getdate(paid_on) > getdate(today()):
		frappe.throw(_("A payment cannot be made on a future date."), frappe.ValidationError)
	doc = _load(name, "Approved")
	doc.move("Paid", _("Paid by {0} on {1}").format(payment_mode, frappe.format(paid_on, "Date"))
		+ (f" ({payment_reference.strip()})" if (payment_reference or "").strip() else ""),
		paid_on=paid_on, payment_mode=payment_mode, payment_reference=(payment_reference or "").strip() or None,
		paid_by=frappe.session.user)
	return doc.status


def raise_claim(installation, task_code, amount, description, expense_date=None, remarks=None, receipt=None,
                source_doctype=None, source_document=None, claimant=None):
	"""A new claim, Pending Approval, for `claimant` (the caller) against a job's task."""
	doc = frappe.get_doc({
		"doctype": "Expense Reimbursement",
		"claimant": claimant or frappe.session.user,
		"solar_installation": installation,
		"task_code": task_code,
		"amount": flt(amount),
		"description": (description or "").strip(),
		"expense_date": expense_date or today(),
		"remarks": (remarks or "").strip() or None,
		"receipt": receipt,
		"source_doctype": source_doctype,
		"source_document": source_document,
	})
	doc.insert()
	return doc
