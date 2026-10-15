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

from a3_sola.api import documents
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

#: Fields the bank documents print; a change re-prints the lender pack.
PRINTED_FIELDS = (
	"lender", "lender_branch", "consumer_name", "installation_address", "district", "state", "pincode", "place",
	"national_portal_application_id", "discom_consumer_id", "discom_id", "jan_samarth_id", "loan_sanction_no",
	"feasibility_status", "capacity_applied_kw", "capacity_installable_kw", "project_cost_all_inclusive",
)

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
		self.fill_from_job()
		self.pull_survey_evidence()
		self.pull_payee_block()
		self.compute_disbursement()
		self.guard_ehs()

	def fill_from_job(self):
		"""What the bank's documents print and the job already knows, for each field still
		blank. A value typed here - a branch the loan is actually with - is never replaced."""
		if not self.solar_installation:
			return
		for field, value in loan_defaults(self.solar_installation).items():
			if value not in (None, "") and self.get(field) in (None, "", 0):
				self.set(field, value)

	def pull_survey_evidence(self):
		"""This is what the feasibility report and EHS checklist print. The feasibility status
		and capacities are the survey's unless they were entered here; EHS is the survey's."""
		estimate = frappe.db.get_value(
			"Solar Installation", self.solar_installation, "solar_design_estimate"
		)
		survey = (
			frappe.db.get_value("Solar Design Estimate", estimate, "site_survey") if estimate else None
		)
		if not survey:
			return
		doc = frappe.get_cached_doc("Site Survey", survey)
		self.feasibility_status = self.feasibility_status or doc.feasibility_status
		self.capacity_applied_kw = self.capacity_applied_kw or doc.capacity_applied_kw
		self.capacity_installable_kw = self.capacity_installable_kw or doc.capacity_installable_kw or doc.total_usable_kw
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
		# What the bank's documents print changed: the pack is printed again, never stale.
		if any(self.has_value_changed(f) for f in PRINTED_FIELDS):
			self.generate_lender_pack()

	def push_to_installation(self):
		was_financed = frappe.db.get_value("Solar Installation", self.solar_installation, "is_financed")
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
		if not was_financed:
			# A loan on a job sold as self-funded: its loan tasks apply now, as when the
			# project is edited to Financed (stages.reapply_applicability).
			from a3_sola.api import stages

			installation = frappe.get_doc("Solar Installation", self.solar_installation)
			changed = stages.reapply_applicability(installation)
			if changed:
				stages._save(installation, _("Loan application {0}: tasks updated: {1}.").format(
					self.name, "; ".join("{0}: {1}".format(name, _("now applies")) for name, _state, _reason in changed)))

	def generate_lender_pack(self):
		"""Vendor feasibility report, EHS checklist, covering letter and the project proposal.

		Each on its own footing: the bank gets whatever rendered, and the row says what did.
		"""
		# Every one in the registered vendor's (RIM) format - the proposal too, not the
		# customer's own Renewcore copy.
		for code in ("BANK-COVERING-LOAN", "BANK-VENDOR-FEASIBILITY", "BANK-EHS-CHECKLIST", "BANK-PROJECT-PROPOSAL"):
			try:
				result = documents.generate_document(
					self.solar_installation, code, source_doctype=self.doctype, source_name=self.name
				)
				self._record_generated(code, result["template"], result["file_url"], result["template_name"], result["template_version"])
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"a3_sola: lender pack for {self.name}")
				self._record_generated(code, code, None, status="Failed")
		if self.generated:
			self.db_update()
			for row in self.generated:
				row.db_update()

	def _record_generated(self, code, document_name, file_url, template_name=None, version=None, status="Generated"):
		row = next((r for r in self.generated if r.template_code == code), None) or self.append(
			"generated", {"template_code": code}
		)
		row.update(
			{
				"document_name": document_name, "file": file_url, "solar_document_template": template_name,
				"template_version": version, "generated_on": frappe.utils.now_datetime(),
				"generated_by": frappe.session.user, "status": status, "is_stale": 0,
			}
		)
		return row

	def attach_project_proposal(self):
		"""The proposal the customer accepted goes to the bank as the project report."""
		proposal = frappe.db.get_value("Solar Installation", self.solar_installation, "solar_proposal")
		if not proposal:
			return None
		file_url = frappe.db.get_value("Solar Proposal", proposal, "proposal_pdf")
		if not file_url:
			from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import generate_proposal

			generate_proposal(proposal)
			file_url = frappe.db.get_value("Solar Proposal", proposal, "proposal_pdf")
		if not file_url:
			return None
		source = frappe.get_doc("File", {"file_url": file_url})
		copy = frappe.get_doc(
			{
				"doctype": "File", "file_name": f"Proposal-{proposal}.pdf", "attached_to_doctype": self.doctype,
				"attached_to_name": self.name, "is_private": 1, "content": source.get_content(),
			}
		).insert(ignore_permissions=True)
		self._record_generated("PROPOSAL", _("Project proposal {0}").format(proposal), copy.file_url)
		documents.register_document(
			self.solar_installation, "LOAN", self.doctype, self.name, _("Project proposal"), copy.file_url, kind="Generated"
		)
		return copy.file_url


def loan_defaults(installation):
	"""Everything the bank covering letter and the vendor feasibility report print that the
	job already knows, as Loan Application values: who and where, the DISCOM and portal
	identifiers, the bank, the survey's feasibility and the cost. A new application starts
	with them (the project board's Loan Documents task) and a blank one is filled on save."""
	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	consumer = (
		frappe.db.get_value(
			"Solar Consumer", inst.solar_consumer,
			["consumer_name", "consumer_number", "discom_id", "discom_section", "national_portal_consumer_id",
			 "installation_address"],
			as_dict=True,
		) if inst.solar_consumer else None
	) or frappe._dict()
	section_name = inst.get("discom_section") or consumer.discom_section
	section = (
		frappe.db.get_value("DISCOM Section", section_name, ["section_code", "district"], as_dict=True)
		if section_name else None
	) or frappe._dict()
	address_name = inst.get("installation_address") or consumer.installation_address
	address = (
		frappe.db.get_value(
			"Address", address_name,
			["address_line1", "address_line2", "city", "county", "state", "pincode"], as_dict=True,
		) if address_name else None
	) or frappe._dict()
	survey = _survey_of(inst)
	district = section.district or address.county or address.city
	return {
		"consumer_name": consumer.consumer_name or inst.get("consumer_name"),
		"discom_consumer_id": inst.get("consumer_number") or consumer.consumer_number,
		# The DISCOM ID is the section office's code - "Chalakudy - 5661" is 5661.
		"discom_id": section.section_code or consumer.discom_id or inst.get("discom_id"),
		"national_portal_application_id": inst.get("national_portal_application_id") or consumer.national_portal_consumer_id,
		"jan_samarth_id": inst.get("jan_samarth_id"),
		"loan_sanction_no": inst.get("loan_sanction_no"),
		"lender": inst.get("lender"),
		"lender_branch": inst.get("lender_branch"),
		"installation_address": ", ".join(p for p in (address.address_line1, address.address_line2, address.city) if p),
		"district": district,
		"state": address.state or (frappe.db.get_value("DISCOM", inst.discom, "state") if inst.get("discom") else None),
		"pincode": address.pincode,
		"place": district,
		"feasibility_status": survey.feasibility_status if survey else None,
		"capacity_applied_kw": survey.capacity_applied_kw if survey else None,
		"capacity_installable_kw": (survey.capacity_installable_kw or survey.total_usable_kw) if survey else None,
		"quotation": inst.get("quotation"),
		"project_cost_all_inclusive": inst.get("gross_contract_value"),
	}


def _survey_of(inst):
	"""The site survey the job was sized against: its estimate's, else its own."""
	survey = (
		frappe.db.get_value("Solar Design Estimate", inst.solar_design_estimate, "site_survey")
		if inst.get("solar_design_estimate") else None
	) or inst.get("site_survey")
	if not survey:
		return None
	return frappe.db.get_value(
		"Site Survey", survey,
		["feasibility_status", "capacity_applied_kw", "capacity_installable_kw", "total_usable_kw"], as_dict=True,
	)
