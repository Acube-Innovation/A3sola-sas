# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The electricity connection, not the person.

One Customer may hold several connections, so this is a separate document linked to
Customer rather than fields on Customer.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

LINKS = (
	("customer", "Customer"),
	("discom", "DISCOM"),
	("discom_section", "DISCOM Section"),
	("roof_type", "Roof Type"),
)


class SolarConsumer(Document):
	def autoname(self):
		set_name(self, "consumer_series_prefix", ".YYYY.-.#####", fallback="SOL-CON")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_consumer_number_unique()
		self.compute_annual_consumption()
		self.compose_gps()
		self.validate_bank_details()

	def validate_consumer_number_unique(self):
		"""A consumer number is unique per DISCOM. Point at the existing record, don't just refuse."""
		if not (self.consumer_number and self.discom):
			return
		existing = frappe.db.get_value(
			"Solar Consumer",
			{"consumer_number": self.consumer_number, "discom": self.discom, "name": ["!=", self.name]},
			["name", "consumer_name"],
			as_dict=True,
		)
		if existing:
			frappe.throw(
				_("Consumer number {0} on {1} already exists as {2} ({3}).").format(
					frappe.bold(self.consumer_number),
					self.discom,
					frappe.utils.get_link_to_form("Solar Consumer", existing.name),
					existing.consumer_name,
				),
				title=_("Duplicate Consumer Number"),
			)

	def compute_annual_consumption(self):
		cycles = 12 if self.billing_frequency == "Monthly" else 6
		self.annual_consumption_units = flt(self.avg_consumption_units) * cycles

	def compose_gps(self):
		if self.latitude and self.longitude:
			self.gps_coordinates = f"{flt(self.latitude, 6)}, {flt(self.longitude, 6)}"
		else:
			self.gps_coordinates = None

	def validate_bank_details(self):
		"""The DBT and the 80% registration refund both land in this account.

		A wrong IFSC is a failed transfer discovered weeks later, and a name mismatch is
		the single most common reason a DBT bounces — so warn, loudly, but do not block:
		the account is often supplied after the survey.
		"""
		if self.bank_ifsc_code:
			self.bank_ifsc_code = self.bank_ifsc_code.strip().upper()
			if not IFSC_PATTERN.match(self.bank_ifsc_code):
				frappe.throw(
					_("IFSC code {0} is not valid. Expected four letters, a zero, then six alphanumerics.").format(
						frappe.bold(self.bank_ifsc_code)
					)
				)
		if (
			self.bank_account_holder_name
			and self.consumer_name
			and self.bank_account_holder_name.strip().lower() != self.consumer_name.strip().lower()
		):
			frappe.msgprint(
				_("Bank account holder {0} differs from the consumer name {1}. A mismatch is the most common cause of a failed Direct Benefit Transfer — confirm it is intended.").format(
					frappe.bold(self.bank_account_holder_name), frappe.bold(self.consumer_name)
				),
				title=_("Check Bank Details"),
				indicator="orange",
			)

	def set_status(self, status):
		"""Status advances through the sales journey and is never set by hand."""
		order = ["New", "Surveyed", "Designed", "Proposed", "Quoted", "Converted"]
		if status == "Dropped" or self.status == "Dropped":
			pass
		elif self.status in order and status in order and order.index(status) < order.index(self.status):
			# never walk the status backwards on a re-submit
			return
		self.db_set("status", status, update_modified=False)
