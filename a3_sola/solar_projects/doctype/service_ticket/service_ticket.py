# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Customer complaints with hard SLAs.

A breached SLA here is a registration risk, not a service metric: the ministry's grievance
framework permits temporary deactivation of vendors that fail to address complaints. Every
escalation is logged so the compliance report can prove the client acted.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from a3_sola.api import sla
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("om_contract", "Solar OM Contract"),
	("project", "Project"),
	("solar_installation", "Solar Installation"),
	("om_visit", "Solar OM Visit"),
	("installation_snag", "Installation Snag"),
	("warranty_claim", "Solar Warranty Claim"),
)


class ServiceTicket(Document):
	def autoname(self):
		set_name(self, "service_ticket_series_prefix", ".YYYY.-.#####", fallback="SOL-TKT")

	def validate(self):
		assert_same_company(self, LINKS)
		self.pull_context()
		self.default_severity()
		sla.compute_sla(self)
		sla.stamp_progress(self)
		self.roll_to_contract()

	def pull_context(self):
		contract = frappe.get_cached_doc("Solar OM Contract", self.om_contract)
		self.project = contract.project
		self.solar_installation = contract.solar_installation
		self.customer = contract.customer

	def default_severity(self):
		"""No generation is critical; low generation is major; anything else is minor."""
		if self.severity:
			return
		self.severity = {
			"No Generation": "Critical",
			"Inverter Fault": "Critical",
			"Earthing": "Critical",
			"Low Generation": "Major",
			"Module Damage": "Major",
		}.get(self.category, "Minor")

	def roll_to_contract(self):
		if self.is_new() or not self.om_contract:
			return
		frappe.db.set_value(
			"Solar OM Contract",
			self.om_contract,
			"open_tickets",
			frappe.db.count(
				"Service Ticket",
				{
					"om_contract": self.om_contract,
					"status": ["not in", ["Resolved", "Closed"]],
					"docstatus": ["<", 2],
				},
			),
			update_modified=False,
		)

	def before_update_after_submit(self):
		sla.handle_reopen(self)
		sla.stamp_progress(self)

	def on_update_after_submit(self):
		self.roll_to_contract()
		if self.status in ("Resolved", "Closed") and not self.closed_on:
			self.db_set("closed_on", now_datetime(), update_modified=False)
