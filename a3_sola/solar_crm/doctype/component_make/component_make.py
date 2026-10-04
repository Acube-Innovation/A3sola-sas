# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from a3_sola.api.uniqueness import assert_unique_in_company


class ComponentMake(Document):
	def validate(self):
		# Per company, not globally: every tenant maintains its own make list.
		assert_unique_in_company(self, ["make_name", "component_type"])
		self.validate_technology()

	def validate_technology(self):
		if not self.technology:
			return
		tech = frappe.db.get_value(
			"Component Technology", self.technology, ["technology_name", "component_type"], as_dict=True
		)
		ctype = tech.component_type if tech else None
		if ctype and ctype != self.component_type:
			frappe.throw(
				_("Technology {0} is for {1}, not {2}.").format(
					frappe.bold(tech.technology_name), ctype, self.component_type
				),
				title=_("Technology Mismatch"),
			)
