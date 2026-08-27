# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Defect management.

A critical snag is not a quality metric - the ministry can temporarily deactivate a vendor
over unresolved defects, so an open critical or major snag blocks PCR.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, today

from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_int, get_value

LINKS = (
	("solar_installation", "Solar Installation"),
	("rectification_work_order", "Installation Work Order"),
)


class InstallationSnag(Document):
	def autoname(self):
		set_name(self, "snag_series_prefix", ".YYYY.-.#####", fallback="SOL-SNAG")

	def validate(self):
		assert_same_company(self, LINKS)
		self.default_severity_by_category()
		self.set_target_closure()

	def default_severity_by_category(self):
		"""Safety and earthing defects are critical - they are what hurt people.

		Severity carries no field default, so an unset severity means "not yet decided" and
		the category rule can fill it. A deliberately chosen severity is respected.
		"""
		if self.severity:
			return
		self.severity = (
			"Critical" if self.category in ("Safety", "Earthing & Surge Protection") else "Minor"
		)

	def set_target_closure(self):
		if self.target_closure_date or not self.reported_on:
			return
		days = {
			"Critical": get_int("critical_snag_sla_days", 3) or 3,
			"Major": 15,
			"Minor": 30,
		}.get(self.severity, 30)
		self.target_closure_date = add_days(self.reported_on, days)

	def after_insert(self):
		if self.severity == "Critical":
			self.notify_escalation_role()

	def notify_escalation_role(self):
		role = get_value("escalation_role")
		if not role:
			return
		holders = frappe.get_all(
			"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", limit=5
		)
		for user in holders:
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": user,
					"date": today(),
					"priority": "High",
					"description": _("Critical snag {0} on {1}: {2}").format(
						self.name, self.solar_installation, self.description[:140]
					),
					"reference_type": "Installation Snag",
					"reference_name": self.name,
				}
			).insert(ignore_permissions=True)

	def on_update(self):
		self.roll_to_installation()

	def on_submit(self):
		self.roll_to_installation()

	def roll_to_installation(self):
		if not self.solar_installation:
			return
		frappe.db.set_value(
			"Solar Installation",
			self.solar_installation,
			{
				"open_snag_count": frappe.db.count(
					"Installation Snag",
					{
						"solar_installation": self.solar_installation,
						"status": ["in", ["Open", "In Progress"]],
						"docstatus": ["<", 2],
					},
				),
				"critical_snag_count": frappe.db.count(
					"Installation Snag",
					{
						"solar_installation": self.solar_installation,
						"severity": "Critical",
						"status": ["in", ["Open", "In Progress"]],
						"docstatus": ["<", 2],
					},
				),
			},
			update_modified=False,
		)
