# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from a3_sola.api.uniqueness import assert_unique_in_company


class SolarGSTValuationRule(Document):
	def validate(self):
		assert_unique_in_company(self, ["rule_name"])
		self.validate_split()
		if self.effective_to and getdate(self.effective_to) <= getdate(self.effective_from):
			frappe.throw(_("Effective To must be after Effective From."))

	def validate_split(self):
		if self.valuation_mode == "Single Rate":
			return
		total = flt(self.goods_value_percent) + flt(self.services_value_percent)
		if flt(total, 2) != 100:
			frappe.throw(
				_("Goods and services percentages total {0}%. They must total exactly 100%.").format(
					flt(total, 2)
				)
			)
