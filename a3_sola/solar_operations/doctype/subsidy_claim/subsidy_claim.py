# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Subsidy claim tracking. POSTS NOTHING.

The subsidy is a Direct Benefit Transfer from the government to the CUSTOMER's bank account
after commissioning. It is never the company's revenue.

Where the company quoted net of subsidy, it has funded that amount and recovers it only
when the customer's DBT lands and is passed over - up to Rs 78,000 a job, which across 200
jobs is over a crore of invisible working capital. Both models are tracked here; the
accounting is Phase 3's, through the extension points in `a3_sola.api.stages`.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate, today

from a3_sola.api import stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (("solar_installation", "Solar Installation"), ("subsidy_scheme", "Subsidy Scheme"))


class SubsidyClaim(Document):
	def autoname(self):
		set_name(self, "subsidy_claim_series_prefix", ".YYYY.-.#####", fallback="SOL-CLM")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_one_per_installation()
		self.compute_ageing()
		self.compute_recovery()

	def validate_one_per_installation(self):
		existing = frappe.db.get_value(
			"Subsidy Claim",
			{"solar_installation": self.solar_installation, "name": ["!=", self.name], "docstatus": ["<", 2]},
			"name",
		)
		if existing:
			frappe.throw(
				_("Installation {0} already has subsidy claim {1}.").format(
					self.solar_installation, frappe.utils.get_link_to_form("Subsidy Claim", existing)
				)
			)

	def compute_ageing(self):
		self.days_since_pcr = (
			date_diff(today(), getdate(self.pcr_uploaded_on)) if self.pcr_uploaded_on else 0
		)
		self.variance_amount = flt(self.disbursed_amount) - flt(self.expected_subsidy_amount) if self.disbursed_on else 0

	def compute_recovery(self):
		if self.claim_model != "Company Funded Gap":
			self.recovery_status = "Not Applicable"
			self.outstanding_recovery = 0
			return
		recoverable = flt(self.amount_recoverable_from_customer) or flt(self.disbursed_amount) or flt(
			self.expected_subsidy_amount
		)
		self.amount_recoverable_from_customer = recoverable
		self.outstanding_recovery = recoverable - flt(self.amount_recovered)
		if not flt(self.amount_recovered):
			self.recovery_status = "Pending"
		elif self.outstanding_recovery > 0:
			self.recovery_status = "Partially Recovered"
		else:
			self.recovery_status = "Fully Recovered"

	def before_submit(self):
		self.gate_pcr()

	def gate_pcr(self):
		"""PCR cannot be recorded on an uncommissioned job or over an open critical defect."""
		if not self.pcr_uploaded_on:
			return
		commissioning = frappe.db.get_value(
			"Commissioning Report", {"solar_installation": self.solar_installation, "docstatus": 1}, "name"
		)
		if not commissioning:
			frappe.throw(
				_("PCR cannot be recorded before the commissioning report for {0} is submitted.").format(
					self.solar_installation
				),
				title=_("Not Commissioned"),
			)
		blocking = frappe.get_all(
			"Installation Snag",
			filters={
				"solar_installation": self.solar_installation,
				"severity": ["in", ["Critical", "Major"]],
				"status": ["in", ["Open", "In Progress"]],
				"docstatus": ["<", 2],
			},
			pluck="name",
		)
		if blocking:
			frappe.throw(
				_("PCR is blocked while {0} critical or major snag(s) remain open: {1}.").format(
					len(blocking), ", ".join(blocking)
				),
				title=_("Open Snags"),
			)

	def on_submit(self):
		# PHASE 3 CONTRACT: the receivable posting registers here. This module posts nothing.
		stages.on_subsidy_claim_submitted(self)

	def before_update_after_submit(self):
		"""Disbursement and recovery are recorded long after submission."""
		self.compute_ageing()
		self.compute_recovery()
		self.handle_status_change()

	def handle_status_change(self):
		"""A query or rejection opens a correction; the row is the task's evidence.

		The correction task blocks while a row is open and completes when every row has
		been corrected and resubmitted; `tasks.sync_from_document` reads the rows.
		"""
		if self.claim_status in ("Query Raised", "Rejected") and not any(
			not r.correction_done or not r.resubmitted_on for r in self.corrections
		):
			self.append(
				"corrections",
				{
					"raised_on": frappe.utils.today(),
					"raised_by": "National Portal",
					"reason": (self.query_description or "").strip() or _("{0} on the national portal").format(self.claim_status),
				},
			)
		self.open_corrections = len([r for r in self.corrections if not (r.correction_done and r.resubmitted_on)])

	def on_update_after_submit(self):
		if self.claim_model == "Company Funded Gap" and flt(self.amount_recovered):
			stages.on_subsidy_recovery_recorded(self)


# ------------------------------------------------------------------ correction actions
@frappe.whitelist()
def record_correction(subsidy_claim, row_name, corrected_on=None, attachment=None, remarks=None):
	"""One correction made. Resubmission is a separate act; the portal may take several."""
	doc = frappe.get_doc("Subsidy Claim", subsidy_claim)
	doc.check_permission("write")
	row = next((r for r in doc.corrections if r.name == row_name), None)
	if not row:
		frappe.throw(_("Correction row not found."))
	row.correction_done = 1
	row.corrected_on = corrected_on or frappe.utils.today()
	if attachment:
		row.attachment = attachment
	if remarks:
		row.remarks = remarks
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return doc.name


@frappe.whitelist()
def mark_resubmitted(subsidy_claim, resubmitted_on=None):
	"""Every corrected row goes back to the portal together; the claim is under verification again."""
	from a3_sola.api import documents

	doc = frappe.get_doc("Subsidy Claim", subsidy_claim)
	doc.check_permission("write")
	pending = [r for r in doc.corrections if not r.resubmitted_on]
	if not pending:
		frappe.throw(_("There is nothing to resubmit."))
	if any(not r.correction_done for r in pending):
		frappe.throw(_("Record every correction as done before resubmitting."), title=_("Corrections Open"))
	on = resubmitted_on or frappe.utils.today()
	for row in pending:
		row.resubmitted_on = on
		if row.attachment:
			documents.register_document(
				doc.solar_installation, "CORR", doc.doctype, doc.name,
				_("Correction proof ({0})").format(frappe.utils.formatdate(row.raised_on)), row.attachment,
				kind="Uploaded", document_date=row.corrected_on, save=True,
			)
	if doc.claim_status in ("Query Raised", "Rejected"):
		doc.claim_status = "Under Verification"
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return doc.name
