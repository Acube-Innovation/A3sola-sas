# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Statutory fees paid on the customer's behalf, and the 80% refund.

The client pays the DISCOM and recovers it against receipts; 80% of the registration base
comes back after commissioning. Today that is tracked nowhere. Every amount here is
resolved from the fee schedule and never typed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate, today

from a3_sola.api import stages, statutory
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_int

LINKS = (("solar_installation", "Solar Installation"), ("solar_consumer", "Solar Consumer"))


class StatutoryFeePayment(Document):
	def autoname(self):
		set_name(self, "statutory_fee_payment_series_prefix", ".YYYY.-.#####", fallback="SOL-SFP")

	def validate(self):
		assert_same_company(self, LINKS)
		self.resolve_amounts()
		self.compute_reimbursement()
		self.compute_refund()
		self.require_receipt()

	def resolve_amounts(self):
		"""Never typed. A typed fee is how the client's templates drifted apart."""
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		fees = statutory.get_statutory_fees(
			installation.discom,
			installation.connection_type or "Single Phase",
			installation.capacity_kw,
			installation.net_meter_mode or "Purchased by Customer",
			on_date=self.payment_date,
			company=self.company,
		)
		self.statutory_fee_schedule = fees["schedule"]

		if self.fee_type == "Application Fee":
			self.amount_base = fees["application_fee_base"]
			self.amount_gst = fees["application_fee_gst"]
			self.amount_gross = fees["application_fee_gross"]
			self.refundable_amount = 0
		elif self.fee_type == "Registration Fee":
			self.amount_base = fees["registration_fee_base"]
			self.amount_gst = fees["registration_fee_gst"]
			self.amount_gross = fees["registration_fee_gross"]
			self.refundable_amount = fees["registration_refundable"]
		elif self.fee_type == "Net Meter Charge":
			self.amount_base = fees["net_meter_charge"]
			self.amount_gst = 0
			self.amount_gross = fees["net_meter_charge"]
			self.refundable_amount = 0

	def compute_reimbursement(self):
		if self.paid_by != "Company on Behalf of Customer":
			self.reimbursable_from_customer = 0
			self.reimbursement_status = "Not Applicable"
			return
		self.reimbursable_from_customer = flt(self.amount_gross)
		recovered = flt(self.reimbursed_amount)
		if not recovered:
			self.reimbursement_status = "Pending"
		elif recovered < flt(self.reimbursable_from_customer):
			self.reimbursement_status = "Partially Recovered"
		else:
			self.reimbursement_status = "Fully Recovered"

	def compute_refund(self):
		if self.fee_type != "Registration Fee":
			self.refund_status = "Not Due"
			return
		self.refund_variance = flt(self.refund_received_amount) - flt(self.refundable_amount) if self.refund_received_on else 0

		if self.refund_received_on:
			self.refund_status = (
				"Short Received" if flt(self.refund_received_amount) < flt(self.refundable_amount) else "Received"
			)
		elif self.refund_claimed_on:
			self.refund_status = "Claimed"
		elif self._refund_due():
			self.refund_status = "Due"
		else:
			self.refund_status = "Not Due"

	def _refund_due(self):
		"""Due once commissioning is complete plus the configured lead time."""
		commissioned = frappe.db.get_value(
			"Installation Stage Log",
			{"parent": self.solar_installation, "stage_code": "COMM", "status": "Completed"},
			"actual_completion_date",
		)
		if not commissioned:
			return False
		lead = get_int("refund_claim_lead_days_after_commissioning", 15) or 15
		return getdate(today()) >= add_days(getdate(commissioned), lead)

	def require_receipt(self):
		if self.paid_by == "Company on Behalf of Customer" and self.docstatus == 1 and not self.receipt:
			frappe.throw(
				_("Attach the payment receipt. Without it the amount cannot be reimbursed by the customer."),
				title=_("Receipt Required"),
			)

	def on_submit(self):
		self.push_to_installation()
		# PHASE 3 CONTRACT: the reimbursement receivable registers here.
		stages.on_statutory_fee_recorded(self)

	def before_update_after_submit(self):
		"""The refund is claimed and received months later; recompute before the write."""
		self.compute_reimbursement()
		self.compute_refund()

	def on_update_after_submit(self):
		self.push_to_installation()
		if self.refund_received_on:
			stages.on_statutory_refund_received(self)
			self.advance_refund_stage()

	def push_to_installation(self):
		updates = {"refund_status": self.refund_status}
		if self.fee_type == "Registration Fee":
			updates["registration_fee_paid_on"] = self.payment_date
			updates["refund_received_amount"] = flt(self.refund_received_amount)
		frappe.db.set_value("Solar Installation", self.solar_installation, updates, update_modified=False)

	def advance_refund_stage(self):
		status = frappe.db.get_value(
			"Installation Stage Log", {"parent": self.solar_installation, "stage_code": "RFND"}, "status"
		)
		if status in (None, "Completed", "Skipped"):
			return
		try:
			stages.advance_stage(
				self.solar_installation, "RFND", actual_date=self.refund_received_on
			)
		except frappe.ValidationError as exc:
			frappe.msgprint(_("RFND stage not advanced: {0}").format(exc), indicator="orange")
