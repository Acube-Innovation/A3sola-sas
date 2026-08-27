# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from a3_sola.api.uniqueness import assert_unique_in_company


class GridRegulationRule(Document):
	def validate(self):
		assert_unique_in_company(self, ["rule_code"])
		if self.rule_type == "Phase Requirement" and not self.required_connection_type:
			frappe.throw(_("A Phase Requirement rule must state the required connection type."))
		if self.is_stayed and not (self.stayed_until or self.stayed_from):
			frappe.throw(_("A stayed rule must record at least a stay start or a stay expiry date."))
		if self.stayed_from and self.stayed_until and getdate(self.stayed_until) < getdate(self.stayed_from):
			frappe.throw(_("Stayed Until must not be before Stayed From."))
