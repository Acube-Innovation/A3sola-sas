# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from a3_sola.api.uniqueness import assert_unique_in_company


class ComponentMake(Document):
	def validate(self):
		# Per company, not globally: every tenant maintains its own make list.
		assert_unique_in_company(self, ["make_name", "component_type"])
