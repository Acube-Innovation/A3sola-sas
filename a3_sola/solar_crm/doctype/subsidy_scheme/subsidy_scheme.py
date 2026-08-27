# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from a3_sola.api.uniqueness import assert_unique_in_company


class SubsidyScheme(Document):
	def validate(self):
		assert_unique_in_company(self, ["scheme_name"])
		self.validate_dates()
		self.validate_slabs()

	def validate_dates(self):
		if self.effective_from and self.effective_to and getdate(self.effective_to) <= getdate(self.effective_from):
			frappe.throw(_("Effective To must be after Effective From."))

	def validate_slabs(self):
		"""Slabs must be ascending, non-overlapping and contiguous.

		A gap between slabs is a capacity that silently returns zero subsidy, which reaches
		a customer proposal as a missing Rs 78,000.
		"""
		rows = sorted(self.slabs, key=lambda r: flt(r.capacity_from_kw))
		previous = None
		for row in rows:
			if flt(row.capacity_to_kw) < flt(row.capacity_from_kw):
				frappe.throw(_("Slab {0}: To must not be less than From.").format(row.idx))
			if previous is not None:
				if flt(row.capacity_from_kw) < flt(previous.capacity_to_kw):
					frappe.throw(
						_("Slabs {0} and {1} overlap between {2} and {3} kW.").format(
							previous.idx, row.idx, row.capacity_from_kw, previous.capacity_to_kw
						)
					)
				gap = flt(row.capacity_from_kw) - flt(previous.capacity_to_kw)
				if gap > 0.011:
					frappe.throw(
						_("Slabs {0} and {1} leave a gap between {2} and {3} kW. A capacity in the gap would silently return no subsidy.").format(
							previous.idx, row.idx, previous.capacity_to_kw, row.capacity_from_kw
						)
					)
			previous = row
