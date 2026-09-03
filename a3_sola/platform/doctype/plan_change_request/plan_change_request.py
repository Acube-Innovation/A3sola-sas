# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api.naming import set_name


class PlanChangeRequest(Document):
	def autoname(self):
		set_name(self, "plan_change_series_prefix", ".YYYY.-.#####", fallback="PCHG")

	def validate(self):
		if self.new_plan == self.current_plan and (
			not self.new_cycle or self.new_cycle == self.current_cycle
		):
			frappe.throw(_("This changes nothing: same plan, same cycle."))

	def on_submit(self):
		# Nothing is applied on submit. A downgrade waits for the boundary and an upgrade
		# waits for payment - both are driven by `apply_plan_change`, never by a save.
		pass

	@frappe.whitelist()
	def apply_now(self):
		from a3_sola.api.lifecycle import plan_change

		return plan_change.apply_plan_change(self.name)
