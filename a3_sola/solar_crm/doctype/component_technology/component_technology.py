# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from a3_sola.api.uniqueness import assert_unique_in_company


class ComponentTechnology(Document):
	def validate(self):
		# Per company, not globally: every tenant maintains its own technology list.
		assert_unique_in_company(self, ["technology_name", "component_type"])


def technology_name(name):
	"""The readable technology behind a Component Technology link, or "" when unset."""
	return (frappe.db.get_value("Component Technology", name, "technology_name") or "") if name else ""
