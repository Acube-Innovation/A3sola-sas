# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from a3_sola.api.uniqueness import assert_unique_in_company


class RoofType(Document):
	def validate(self):
		# Per company, not globally: every tenant needs its own copy of this master.
		assert_unique_in_company(self, ['roof_type'])
