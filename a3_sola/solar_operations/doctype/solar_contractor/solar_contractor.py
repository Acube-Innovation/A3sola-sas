# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A contractor the company puts to work: electrical, structural or a whole-job EPC.

The crew on a work order is employees or one of these. The electrical contractor is also
who the serial details are mailed to before the completion certificate comes back.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from a3_sola.api.uniqueness import assert_unique_in_company


class SolarContractor(Document):
	def validate(self):
		assert_unique_in_company(self, ["contractor_name"])
		if self.email_id:
			frappe.utils.validate_email_address(self.email_id, throw=True)
		if self.licence_valid_till and getdate(self.licence_valid_till) < getdate(today()):
			# Warn, do not block: an expired licence is a fact to chase, and a contractor
			# already on three jobs cannot be made to vanish from the master.
			frappe.msgprint(
				_("{0}'s licence expired on {1}.").format(self.contractor_name, frappe.format(self.licence_valid_till, "Date")),
				indicator="orange",
			)
