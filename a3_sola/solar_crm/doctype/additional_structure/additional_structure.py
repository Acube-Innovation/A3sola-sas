# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Structure work beyond the package's standard flat-roof mounting."""

from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api import line_charges


class AdditionalStructure(Document):
	def validate(self):
		line_charges.validate(self, lambda row: flt(row.qty) * flt(row.rate))
