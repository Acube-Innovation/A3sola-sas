# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from a3_sola.api.naming import set_name


class SeatChangeRequest(Document):
	def autoname(self):
		set_name(self, "seat_change_series_prefix", ".YYYY.-.#####", fallback="SEAT")

	def validate(self):
		if not cint(self.seat_delta):
			frappe.throw(_("Say how many seats."))
		if cint(self.seat_delta) > 0 and self.change_type != "Add Seats":
			self.change_type = "Add Seats"
		if cint(self.seat_delta) < 0 and self.change_type != "Remove Seats":
			self.change_type = "Remove Seats"

	@frappe.whitelist()
	def apply_now(self):
		from a3_sola.api.lifecycle import seats

		return seats.apply_seat_change(self.name)
