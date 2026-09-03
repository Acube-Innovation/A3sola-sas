# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One suspension, its approval, and the snapshot that makes it reversible."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from a3_sola.api.naming import set_name


class AccessSuspension(Document):
	def autoname(self):
		set_name(self, "suspension_series_prefix", ".YYYY.-.#####", fallback="SUSP")

	def before_insert(self):
		if not self.requested_on:
			self.requested_on = now_datetime()
		if not self.platform_subscription and self.tenant:
			self.platform_subscription = frappe.db.get_value(
				"Tenant", self.tenant, "platform_subscription"
			)

	def on_trash(self):
		if self.status in ("Applied", "Partially Applied", "Restored"):
			frappe.throw(
				_("A suspension that was applied cannot be deleted. It is the record of "
				  "how to put a customer's access back."),
				title=_("Cannot Delete"),
			)

	@frappe.whitelist()
	def approve_now(self, note=None):
		from a3_sola.api.lifecycle import suspension

		return suspension.approve(self.name, note)

	@frappe.whitelist()
	def reject_now(self, reason):
		from a3_sola.api.lifecycle import suspension

		return suspension.reject(self.name, reason)

	@frappe.whitelist()
	def restore_now(self, reason=None):
		from a3_sola.api.lifecycle import access

		return access.restore_tenant_access(
			self.tenant, self.name, trigger="Manual",
			actor=frappe.session.user, reason=reason,
		).name
