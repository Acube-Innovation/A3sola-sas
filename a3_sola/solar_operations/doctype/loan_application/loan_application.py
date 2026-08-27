# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The financed sale.

Money arrives in two tranches - an advance on sanction and the balance after the completion
report - which changes the execution chain and the cash position. Phase 3 consumes the
tranches against billing milestones; this module posts nothing.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api import documents, stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("quotation", "Quotation"),
)


class LoanApplication(Document):
	def autoname(self):
		set_name(self, "loan_application_series_prefix", ".YYYY.-.#####", fallback="SOL-LOAN")

	def validate(self):
		assert_same_company(self, LINKS)
		self.pull_survey_evidence()
		self.pull_payee_block()
		self.compute_disbursement()
		self.guard_ehs()

	def pull_survey_evidence(self):
		"""This is what the feasibility report and EHS checklist print. Never re-entered."""
		estimate = frappe.db.get_value(
			"Solar Installation", self.solar_installation, "solar_design_estimate"
		)
		survey = (
			frappe.db.get_value("Solar Design Estimate", estimate, "site_survey") if estimate else None
		)
		if not survey:
			return
		doc = frappe.get_cached_doc("Site Survey", survey)
		self.feasibility_status = doc.feasibility_status
		self.capacity_applied_kw = doc.capacity_applied_kw
		self.capacity_installable_kw = doc.capacity_installable_kw or doc.total_usable_kw
		self.ehs_overall_status = doc.ehs_overall_status
		self.ehs_conditions = doc.ehs_conditions
		self.structural_certificate_on_file = 1 if doc.structural_safety_certificate else 0

	def pull_payee_block(self):
		"""The lender credits the EPC, not the consumer."""
		company = frappe.get_cached_doc("Company", self.company)
		for field in (
			"payee_legal_name",
			"payee_bank_name",
			"payee_bank_account_no",
			"payee_bank_branch",
			"payee_bank_ifsc",
		):
			self.set(field, company.get(field))

	def compute_disbursement(self):
		total = sum(flt(row.amount) for row in self.disbursements)
		self.total_disbursed = total
		self.outstanding = flt(self.sanctioned_amount) - total
		for row in self.disbursements:
			if row.tranche == "Advance" and not self.advance_received_on:
				self.advance_received_on = row.disbursement_date
			if row.tranche == "Balance":
				self.balance_received_on = row.disbursement_date

	def guard_ehs(self):
		"""A lender will not disburse against a go/no-go failure and neither should we."""
		if self.status == "Not Applied":
			return
		if self.ehs_overall_status == "Blocked":
			frappe.throw(
				_("The site survey is EHS-blocked ({0}). A loan application cannot proceed until it is cleared.").format(
					self.ehs_conditions or _("go/no-go criterion failed")
				),
				title=_("EHS Blocked"),
			)

	def on_submit(self):
		self.push_to_installation()
		self.generate_lender_pack()

	def before_update_after_submit(self):
		"""Tranches arrive months apart; recompute the outstanding before the write."""
		self.compute_disbursement()

	def on_update_after_submit(self):
		self.push_to_installation()
		self.advance_stages()

	def push_to_installation(self):
		frappe.db.set_value(
			"Solar Installation",
			self.solar_installation,
			{
				"is_financed": 1,
				"lender": self.lender,
				"lender_branch": self.lender_branch,
				"loan_application": self.name,
				"jan_samarth_id": self.jan_samarth_id,
				"loan_sanction_no": self.loan_sanction_no,
				"sanctioned_amount": self.sanctioned_amount,
				"disbursed_amount": self.total_disbursed,
				"disbursement_outstanding": self.outstanding,
			},
			update_modified=False,
		)

	def generate_lender_pack(self):
		"""Vendor feasibility report, EHS checklist and covering letter - all from the survey."""
		for code in ("BANK-VENDOR-FEASIBILITY", "BANK-EHS-CHECKLIST", "BANK-COVERING-LOAN"):
			try:
				documents.generate_document(self.solar_installation, code)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"a3_sola: lender pack for {self.name}")

	def advance_stages(self):
		"""The advance tranche advances LOAN; the balance advances BCOM."""
		tranches = {row.tranche for row in self.disbursements if row.amount}
		if "Advance" in tranches:
			self._try_advance("LOAN", _("Advance disbursed by {0}").format(self.lender))
		if "Balance" in tranches:
			self._try_advance("BCOM", _("Balance disbursed by {0}").format(self.lender))

	def _try_advance(self, stage_code, remarks):
		status = frappe.db.get_value(
			"Installation Stage Log",
			{"parent": self.solar_installation, "stage_code": stage_code},
			"status",
		)
		if status in (None, "Completed", "Skipped"):
			return
		try:
			stages.advance_stage(
				self.solar_installation, stage_code, external_reference=self.loan_sanction_no, remarks=remarks
			)
		except frappe.ValidationError as exc:
			frappe.msgprint(
				_("Stage {0} was not advanced: {1}").format(stage_code, exc), indicator="orange"
			)
