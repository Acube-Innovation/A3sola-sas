# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cable runs beyond the package's included length, priced per metre."""

from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api import line_charges


class AdditionalCable(Document):
	def validate(self):
		line_charges.validate(self, lambda row: flt(row.length) * flt(row.rate))
