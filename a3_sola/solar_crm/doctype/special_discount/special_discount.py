# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A discount outside the package's standard one, with who approved it and why."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api import line_charges


class SpecialDiscount(Document):
	def validate(self):
		for row in self.get("items") or []:
			if row.discount_type == "Percentage" and not 0 <= flt(row.discount_value) <= 100:
				frappe.throw(_("Row {0}: a percentage discount must be between 0 and 100.").format(row.idx))
			if row.discount_type == "Percentage" and not flt(row.base_amount):
				frappe.throw(_("Row {0}: enter the base amount the percentage is taken from.").format(row.idx))
		line_charges.validate(self, discount_amount)


def discount_amount(row):
	if row.discount_type == "Percentage":
		return flt(row.base_amount) * flt(row.discount_value) / 100
	return flt(row.discount_value)
