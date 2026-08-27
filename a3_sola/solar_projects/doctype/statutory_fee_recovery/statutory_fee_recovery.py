# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("project", "Project"),
	("solar_installation", "Solar Installation"),
	("statutory_fee_payment", "Statutory Fee Payment"),
)


class StatutoryFeeRecovery(Document):
	def autoname(self):
		set_name(self, "statutory_recovery_series_prefix", ".YYYY.-.#####", fallback="SOL-SFR")

	def validate(self):
		assert_same_company(self, LINKS)
		self.compute()

	def before_update_after_submit(self):
		self.compute()

	def compute(self):
		self.outstanding_reimbursement = flt(
			flt(self.fees_paid_by_company) - flt(self.reimbursed_amount), 2
		)
		recovered = flt(self.reimbursed_amount) + flt(self.refund_received) + flt(self.refund_written_off)
		expected = flt(self.fees_paid_by_company)
		if flt(self.refund_written_off):
			self.status = "Written Off"
		elif not recovered:
			self.status = "Pending"
		elif self.outstanding_reimbursement > 0:
			self.status = "Partially Recovered"
		else:
			self.status = "Fully Recovered"
