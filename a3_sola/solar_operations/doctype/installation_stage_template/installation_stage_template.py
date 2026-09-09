# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The task list a Solar Installation is built from.

One template is shared by every company. It carries no company - and it has to say so
explicitly, because Frappe fills a blank company Link with the site's default company on
insert, which would quietly turn the shared template into one company's.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class InstallationStageTemplate(Document):
	def validate(self):
		if self.is_shared:
			self.company = None
			self.validate_one_shared()

	def validate_one_shared(self):
		other = frappe.db.get_value(
			"Installation Stage Template", {"is_shared": 1, "name": ["!=", self.name]}, "name"
		)
		if other:
			frappe.throw(
				_("{0} is already the template every company shares. Edit it, or give this one a company.").format(
					frappe.utils.get_link_to_form("Installation Stage Template", other)
				),
				title=_("One Shared Template"),
			)
