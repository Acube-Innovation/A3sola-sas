# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DISCOMSection(Document):
	def validate(self):
		existing = frappe.db.get_value(
			"DISCOM Section",
			{
				"section_name": self.section_name,
				"discom": self.discom,
				"company": self.company,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Section {0} already exists for {1} as {2}.").format(
					self.section_name, self.discom, frappe.utils.get_link_to_form("DISCOM Section", existing)
				)
			)
