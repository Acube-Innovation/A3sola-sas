# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ElectricityTariff(Document):
	def validate(self):
		self.validate_slabs()

	def validate_slabs(self):
		"""Telescopic slabs must be ascending, contiguous and non-overlapping."""
		rows = sorted(self.slabs, key=lambda r: flt(r.units_from))
		previous = None
		for row in rows:
			if flt(row.units_to) <= flt(row.units_from):
				frappe.throw(_("Slab {0}: Units To must be greater than Units From.").format(row.idx))
			if previous is not None and flt(row.units_from) != flt(previous.units_to):
				frappe.throw(
					_("Slab {0} must start where slab {1} ends ({2} units); telescopic billing has no gaps.").format(
						row.idx, previous.idx, previous.units_to
					)
				)
			previous = row
