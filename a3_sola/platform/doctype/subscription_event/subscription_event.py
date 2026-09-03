# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The audit spine of the lifecycle. Append-only, for everyone.

Every state change, every access change and every policy decision writes one of these.
Nothing updates or deletes them - a correction is a new event pointing at the old one.

The reason is narrow and practical. Six months after a customer was switched off, someone
will ask why. The answer has to be a record written at the moment it happened by the code
that did it, not a reconstruction from timestamps.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from a3_sola.api.naming import set_name


class SubscriptionEvent(Document):
	def autoname(self):
		set_name(self, "subscription_event_series_prefix", ".YYYY.-.#####", fallback="SEVT")

	def before_insert(self):
		if not self.event_time:
			self.event_time = now_datetime()
		if not self.tenant and self.platform_subscription:
			self.tenant = frappe.db.get_value(
				"Tenant", {"platform_subscription": self.platform_subscription}, "name"
			)

	def on_update(self):
		# `on_update` fires for the insert too, and by then `is_new()` is already False -
		# `flags.in_insert` is the only reliable way to tell the two apart.
		if self.flags.in_insert:
			return
		frappe.throw(
			_("A subscription event cannot be changed once it is written. If it was "
			  "wrong, write a new event saying so."),
			title=_("Events are permanent"),
		)

	def on_trash(self):
		frappe.throw(
			_("A subscription event cannot be deleted. It is the record of why a paying "
			  "customer's access changed."),
			title=_("Events are permanent"),
		)
