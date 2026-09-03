# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from a3_sola.api.naming import set_name


class CancellationRequest(Document):
	def autoname(self):
		set_name(self, "cancellation_series_prefix", ".YYYY.-.#####", fallback="CANC")

	def validate(self):
		if self.cancellation_type == "Immediate" and not self.reason_detail:
			frappe.throw(
				_("An immediate cancellation needs a note saying why it cannot wait for "
				  "the end of the period the customer has paid for.")
			)

	@frappe.whitelist()
	def generate_export(self):
		from a3_sola.api.lifecycle import cancellation

		return cancellation.generate_export(self.name)

	@frappe.whitelist()
	def withdraw_request(self, note=None):
		from a3_sola.api.lifecycle import cancellation

		return cancellation.withdraw(self.name, note)
