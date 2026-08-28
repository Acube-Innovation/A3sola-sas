# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from a3_sola.api.naming import set_name


class TenantInvitation(Document):
	def autoname(self):
		set_name(self, "invitation_series_prefix", ".YYYY.-.#####", fallback="TINV")

	def validate(self):
		self.invited_email = (self.invited_email or "").strip().lower()

	def on_update(self):
		from a3_sola.api.entitlements import recalculate_usage

		if self.tenant and frappe.db.exists("Tenant", self.tenant):
			recalculate_usage(self.tenant)
