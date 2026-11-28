# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One row of Administration > Event Packages (api/event_package_rules): a two-month bill range
and the visitor's answers, and the package an event registration that matches them gets."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class EventPackageRule(Document):
	def validate(self):
		if flt(self.bill_from) < 0 or flt(self.bill_to) < 0:
			frappe.throw(_("A bill amount cannot be below zero."), title=_("Bill Range"))
		if flt(self.bill_to) and flt(self.bill_to) < flt(self.bill_from):
			frappe.throw(_("Bill To ₹{0} is below Bill From ₹{1}.").format(
				frappe.format(self.bill_to, "Currency"), frappe.format(self.bill_from, "Currency")), title=_("Bill Range"))
		company = frappe.db.get_value("Solar Package", self.package, "company")
		if company and company != self.company:
			frappe.throw(_("Package {0} belongs to {1}, not {2}.").format(self.package, company, self.company),
				title=_("Package"))
