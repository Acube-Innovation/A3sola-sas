# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An exhibition, event or campaign where visitors register by scanning a QR code.

The QR opens /register/<public_key> (www/register); the stall screen is
/event-screen/<display_key> (www/event_screen). Two keys, so a visitor holding the QR's link
can never open the screen. Every lead registered here takes the event's company, owner,
source and campaign (api/event_registration) - never what the form sends.
"""

import secrets

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

#: The Lead Source an event's leads get when it names none (seeded by setup/install).
EVENT_SOURCE = "Exhibition"


def new_key():
	return secrets.token_urlsafe(18)


class SolarEvent(Document):
	def before_insert(self):
		self.public_key = new_key()
		self.display_key = new_key()

	def validate(self):
		if self.start_date and self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("The event cannot end before it starts."))
		if not self.lead_source and frappe.db.exists("Lead Source", EVENT_SOURCE):
			self.lead_source = EVENT_SOURCE
		self._check_owner()
		self._check_packages()
		if not self.public_key:
			self.public_key = new_key()
		if not self.display_key:
			self.display_key = new_key()

	def _check_owner(self):
		"""The owner works the leads: an enabled member of the company's staff, not a partner."""
		from a3_sola.api import partner_scope

		user = frappe.db.get_value("User", self.lead_owner, ["enabled", "user_type"], as_dict=True)
		if not user or not user.enabled or user.user_type != "System User" or partner_scope.partner_kinds(self.lead_owner):
			frappe.throw(_("The lead owner must be an active member of staff."))

	def _check_packages(self):
		for row in self.get("estimate_packages") or []:
			company = frappe.db.get_value("Solar Package", row.package, "company")
			if company and company != self.company:
				frappe.throw(_("{0} is another company's package.").format(row.package))

	def after_insert(self):
		self.db_set("campaign", campaign_for(self.event_name), update_modified=False)


def campaign_for(title):
	"""The Campaign named like the event: the one there is, else a new one."""
	name = frappe.db.get_value("Campaign", {"campaign_name": title})
	if name:
		return name
	return frappe.get_doc({"doctype": "Campaign", "campaign_name": title,
		"description": _("Leads registered at the event by QR code.")}).insert(ignore_permissions=True).name
