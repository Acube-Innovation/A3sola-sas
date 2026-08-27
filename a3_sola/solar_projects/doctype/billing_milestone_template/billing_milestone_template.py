# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.uniqueness import assert_unique_in_company


class BillingMilestoneTemplate(Document):
	def validate(self):
		assert_unique_in_company(self, ["template_name"])
		self.validate_total()
		self.validate_one_default()

	def validate_total(self):
		total = flt(sum(flt(row.percentage) for row in self.milestones), 2)
		if total != 100:
			frappe.throw(
				_("Milestone percentages total {0}%. They must total exactly 100%.").format(total),
				title=_("Milestones Do Not Total 100%"),
			)

	def validate_one_default(self):
		if not self.is_default:
			return
		existing = frappe.db.get_value(
			"Billing Milestone Template",
			{
				"company": self.company,
				"is_default": 1,
				"applicable_consumer_category": self.applicable_consumer_category,
				"applicable_net_meter_mode": self.applicable_net_meter_mode,
				"applicable_funding": self.applicable_funding,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("{0} is already the default for this combination.").format(
					frappe.utils.get_link_to_form("Billing Milestone Template", existing)
				)
			)
