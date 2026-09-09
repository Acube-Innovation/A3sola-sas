# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task of an installation that has no document of its own.

Form 1 generation, the advance, the design freeze, a contractor's certificate, a meter
purchase: each is a status, an assignee, a date, what it cost, and the evidence it produced
or received. One doctype carries all of them; the task code decides which section shows.

Completing the task is a two-step act on purpose - status Completed, then submit - because
the installation's task row flips only on submit, and a task somebody is still filling in
must not read as done to everyone else.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from a3_sola.api import documents
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
)

#: What each task must show before it may be called Completed. A field name, or a callable
#: that takes the document and returns a missing-item message or None.
REQUIRED_EVIDENCE = {
	"ADV": ("amount", "paid_on"),
	"BAL": ("amount", "paid_on"),
	"CCERT": ("certificate", "certificate_no"),
	"PORTUPD": ("dcr_certificate",),
	"KTST": ("result", "signed_checklist"),
	"MTR": ("meter_serial",),
	"DSGN": ("bom",),
}

#: Documents a task can generate for itself, by task code.
TASK_DOCUMENTS = {"FRM1": ["KSEB-FORM-1"], "DSGN": ["BOM-SUMMARY"]}

LABELS = {
	"amount": "Amount", "paid_on": "Paid On", "certificate": "Certificate",
	"certificate_no": "Certificate No", "dcr_certificate": "DCR Certificate", "result": "Result",
	"signed_checklist": "Signed Checklist", "meter_serial": "Meter Serial No", "bom": "Bill of Materials",
}


class InstallationTask(Document):
	def autoname(self):
		set_name(self, "installation_task_series_prefix", ".YYYY.-.#####", fallback="SOL-TSK")

	def validate(self):
		self.pull_installation()
		assert_same_company(self, LINKS)
		self.validate_task_code()
		self.validate_one_open()
		self.set_defaults()
		self.stamp_uploads()
		if self.status == "Completed":
			self.require_evidence()

	def pull_installation(self):
		"""The company is the installation's, never the session default."""
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		self.company = installation.company
		if not self.task_name and self.task_code and self.task_code != "OTHER":
			row = next((r for r in installation.stages if r.stage_code == self.task_code), None)
			self.task_name = row.stage_name if row else self.task_code

	def validate_task_code(self):
		"""The code must be one of this installation's tasks that runs in an Installation Task."""
		if self.task_code == "OTHER":
			if not self.task_name:
				frappe.throw(_("Give an ad-hoc task a name."))
			return
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		row = next((r for r in installation.stages if r.stage_code == self.task_code), None)
		if not row:
			frappe.throw(
				_("Task {0} is not on installation {1}.").format(self.task_code, self.solar_installation)
			)
		if row.task_doctype and row.task_doctype != self.doctype:
			frappe.throw(
				_("Task {0} is carried out in a {1}, not here.").format(self.task_code, _(row.task_doctype)),
				title=_("Wrong Document"),
			)

	def validate_one_open(self):
		if self.task_code == "OTHER":
			return
		other = frappe.db.get_value(
			"Installation Task",
			{
				"solar_installation": self.solar_installation,
				"task_code": self.task_code,
				"docstatus": 0,
				"name": ["!=", self.name],
			},
			"name",
		)
		if other:
			frappe.throw(
				_("Task {0} already has an open document, {1}. Finish or delete that one.").format(
					self.task_code, frappe.utils.get_link_to_form("Installation Task", other)
				)
			)

	def set_defaults(self):
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		if not self.assigned_on:
			self.assigned_on = today()
		if self.status == "In Progress" and not self.started_on:
			self.started_on = today()
		if self.status == "Completed" and not self.completed_on:
			self.completed_on = today()
		if self.task_code == "MTR" and flt(self.meter_cost) and not flt(self.cost):
			self.cost = self.meter_cost
			self.cost_category = self.cost_category or "Material"

	def stamp_uploads(self):
		for row in self.uploads or []:
			if not row.uploaded_by:
				row.uploaded_by = frappe.session.user
				row.uploaded_on = frappe.utils.now_datetime()

	def require_evidence(self):
		missing = [
			LABELS.get(field, field)
			for field in REQUIRED_EVIDENCE.get(self.task_code, ())
			if not self.get(field)
		]
		if self.task_code == "FRM1" and not (self.generated or self.uploads):
			missing.append(_("Form 1 (generated or uploaded)"))
		if missing:
			frappe.throw(
				_("Task {0} cannot be completed without: {1}").format(self.task_code, ", ".join(missing)),
				title=_("Evidence Required"),
			)

	def before_submit(self):
		if self.status not in ("Completed", "Skipped"):
			frappe.throw(
				_("Set the status to Completed (or Skipped, with a reason) before submitting."),
				title=_("Not Finished"),
			)

	def on_submit(self):
		"""A bank-funded advance or balance settles the lender's milestone on the plan."""
		if self.task_code not in ("ADV", "BAL") or self.status != "Completed":
			return
		if self.payer != "Bank" or not flt(self.amount):
			return
		try:
			from a3_sola.api import billing

			billing.on_loan_disbursed(
				self.solar_installation, "Advance" if self.task_code == "ADV" else "Balance",
				self.amount, self.payment_reference or self.name,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: lender milestone for {self.name}")


# ------------------------------------------------------------------ form actions
def _load(task, action="write"):
	doc = frappe.get_doc("Installation Task", task)
	doc.check_permission(action)
	return doc


def _save(doc):
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return doc


@frappe.whitelist()
def document_choices(task):
	"""The templates this task can generate: its own list, filtered to what is installed."""
	doc = _load(task, "read")
	codes = TASK_DOCUMENTS.get(doc.task_code, [])
	if not codes:
		return []
	rows = frappe.get_all(
		"Solar Document Template",
		filters={"template_code": ["in", codes], "company": doc.company, "is_active": 1},
		fields=["template_code", "document_name"],
	)
	return [{"code": r.template_code, "name": r.document_name} for r in rows]


@frappe.whitelist()
def generate(task, template_code, force=0):
	"""Generate a document for this task. The PDF attaches here and registers on the job."""
	doc = _load(task)
	result = documents.generate_document(
		doc.solar_installation, template_code, force=force,
		source_doctype=doc.doctype, source_name=doc.name,
	)
	row = next((r for r in doc.generated if r.template_code == result["template_code"]), None)
	if not row:
		row = doc.append("generated", {"template_code": result["template_code"]})
	row.update(
		{
			"solar_document_template": result["template_name"],
			"document_name": result["template"],
			"file": result["file_url"],
			"template_version": result["template_version"],
			"generated_on": frappe.utils.now_datetime(),
			"generated_by": frappe.session.user,
			"status": "Generated",
			"is_stale": 0,
		}
	)
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return result


@frappe.whitelist()
def attach_evidence(task, document_name, file_url, document_date=None, reference_no=None):
	doc = _load(task)
	if not (document_name and file_url):
		frappe.throw(_("A document name and a file are both needed."))
	doc.append(
		"uploads",
		{
			"document_name": document_name,
			"attachment": file_url,
			"document_date": document_date or today(),
			"reference_no": reference_no,
		},
	)
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return doc.name


@frappe.whitelist()
def start(task):
	doc = _load(task)
	if doc.status != "Pending":
		frappe.throw(_("Task {0} has already started.").format(doc.name))
	doc.status = "In Progress"
	doc.started_on = today()
	_save(doc)
	return doc.status


@frappe.whitelist()
def complete(task, completed_on=None):
	"""Status Completed, then submit - the submit is what completes the installation's row."""
	doc = _load(task)
	if doc.docstatus != 0:
		frappe.throw(_("Task {0} is already submitted.").format(doc.name))
	doc.status = "Completed"
	doc.completed_on = completed_on or today()
	doc.save()
	doc.submit()
	return doc.name


@frappe.whitelist()
def skip(task, reason=None):
	"""Not required after all. Manager-only when the installation's row is mandatory."""
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when skipping a task."))
	doc = _load(task)
	if doc.docstatus != 0:
		frappe.throw(_("Task {0} is already submitted.").format(doc.name))
	row = frappe.db.get_value(
		"Installation Stage Log",
		{"parent": doc.solar_installation, "stage_code": doc.task_code},
		"is_mandatory",
	)
	if row:
		from a3_sola.api.stages import _require_manager

		_require_manager(_("skip a mandatory task"))
	doc.status = "Skipped"
	doc.skip_reason = reason.strip()
	doc.save()
	doc.submit()
	return doc.name


@frappe.whitelist()
def pull_loan_tranche(task):
	"""Copy the bank's disbursement onto an advance or balance task, so the figure the bank
	wired is the figure recorded - typed once, on the loan, never twice."""
	doc = _load(task)
	if doc.task_code not in ("ADV", "BAL"):
		frappe.throw(_("Only an advance or balance task takes a bank tranche."))
	# The installation learns its loan on submit; a draft loan already carries the tranche.
	loan = (
		doc.loan_application
		or frappe.db.get_value("Solar Installation", doc.solar_installation, "loan_application")
		or frappe.db.get_value(
			"Loan Application", {"solar_installation": doc.solar_installation, "docstatus": ["<", 2]},
			"name", order_by="creation desc",
		)
	)
	if not loan:
		frappe.throw(_("This installation has no loan application."), title=_("Not Financed"))
	wanted = "Advance" if doc.task_code == "ADV" else "Balance"
	application = frappe.get_doc("Loan Application", loan)
	tranche = next((r for r in application.disbursements if r.tranche == wanted and flt(r.amount)), None)
	if not tranche:
		frappe.throw(_("{0} has no {1} tranche recorded yet.").format(loan, wanted.lower()))
	doc.payer = "Bank"
	doc.loan_application = loan
	doc.loan_tranche = wanted
	doc.amount = tranche.amount
	doc.paid_on = tranche.get("disbursement_date") or today()
	doc.payment_mode = "Loan Disbursement"
	doc.payment_reference = tranche.get("utr_or_reference")
	doc.bank_advice = tranche.get("bank_advice")
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return {"amount": doc.amount, "paid_on": str(doc.paid_on)}
