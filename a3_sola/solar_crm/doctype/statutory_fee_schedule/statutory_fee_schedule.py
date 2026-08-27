# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class StatutoryFeeSchedule(Document):
	def validate(self):
		if self.effective_to and getdate(self.effective_to) <= getdate(self.effective_from):
			frappe.throw(_("Effective To must be after Effective From."))
		if flt(self.registration_refund_percent) > 100 or flt(self.registration_refund_percent) < 0:
			frappe.throw(_("Refundable percentage must be between 0 and 100."))
		self.validate_no_overlap()
		self.validate_net_meter_rows()

	def validate_no_overlap(self):
		"""Two active schedules covering the same DISCOM and date would make the fee ambiguous."""
		if not self.is_active:
			return
		others = frappe.get_all(
			"Statutory Fee Schedule",
			filters={
				"discom": self.discom,
				"company": self.company,
				"is_active": 1,
				"name": ["!=", self.name],
			},
			fields=["name", "effective_from", "effective_to"],
		)
		start = getdate(self.effective_from)
		end = getdate(self.effective_to) if self.effective_to else None
		for other in others:
			o_start = getdate(other.effective_from)
			o_end = getdate(other.effective_to) if other.effective_to else None
			if (end is None or o_start <= end) and (o_end is None or start <= o_end):
				frappe.throw(
					_("Schedule {0} already covers {1} over an overlapping period. Statutory fees must resolve to exactly one schedule.").format(
						frappe.utils.get_link_to_form("Statutory Fee Schedule", other.name), self.discom
					)
				)

	def validate_net_meter_rows(self):
		seen = set()
		for row in self.net_meter_charges:
			key = (row.connection_type, row.supply_mode)
			if key in seen:
				frappe.throw(_("Duplicate net meter row for {0} / {1}.").format(*key))
			seen.add(key)
