# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The DISCOM's net-metering agreement.

Executed on stamp paper, valid twenty-five years, terminable on thirty days' notice by
either party - so it is a record with a life, not a one-off print. SPIN is allotted here
and is the identifier every later document uses.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from a3_sola.api import documents, stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_value

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("commissioning_report", "Commissioning Report"),
)


class NetMeteringAgreement(Document):
	def autoname(self):
		set_name(self, "net_metering_agreement_series_prefix", ".YYYY.-.#####", fallback="SOL-NMA")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_one_active()
		self.pull_schedule()
		self.validate_wheeling()
		if not self.stamp_paper_value:
			self.stamp_paper_value = get_value("stamp_paper_denomination")

	def validate_one_active(self):
		existing = frappe.db.get_value(
			"Net Metering Agreement",
			{
				"solar_installation": self.solar_installation,
				"name": ["!=", self.name],
				"docstatus": 1,
				"is_terminated": 0,
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Installation {0} already has an active agreement, {1}. Terminate it before executing another.").format(
					self.solar_installation, frappe.utils.get_link_to_form("Net Metering Agreement", existing)
				)
			)

	def pull_schedule(self):
		"""Schedules I and II are the consumer record; nothing here is re-typed."""
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		consumer = frappe.get_cached_doc("Solar Consumer", installation.solar_consumer)
		address = (
			frappe.get_cached_doc("Address", consumer.installation_address)
			if consumer.installation_address
			else None
		)

		self.consumer_name = consumer.consumer_name
		self.permanent_address = _address_text(address)
		self.installation_address = _address_text(address)
		self.consumer_number_and_category = f"{consumer.consumer_number} / {consumer.tariff_category or ''}".strip(" /")
		self.connected_load_or_contract_demand = (
			f"{consumer.connected_load_watts:g} W" if consumer.connected_load_watts else None
		)
		self.plant_capacity_kwp = installation.capacity_kw
		self.electrical_section = (
			frappe.db.get_value("DISCOM Section", installation.discom_section, "section_name")
			if installation.discom_section
			else None
		)
		self.local_body_type = consumer.local_body_type
		self.local_body_name = consumer.local_body_name
		self.village = consumer.village
		self.survey_number = consumer.survey_number
		self.gps_coordinates = consumer.gps_coordinates

		if self.commissioning_report and not self.solar_meter_number:
			report = frappe.get_cached_doc("Commissioning Report", self.commissioning_report)
			self.solar_meter_number = report.net_meter_serial_no
			self.solar_meter_make = report.net_meter_make
			self.solar_meter_initial_reading = report.initial_export_reading

	def validate_wheeling(self):
		"""Excess energy may be wheeled to the consumer's other premises, in preference order."""
		seen = set()
		own = frappe.db.get_value("Solar Consumer", self.solar_consumer, "consumer_number")
		for row in self.wheeling_preferences:
			if row.consumer_number == own:
				frappe.throw(
					_("Preference {0} points at this installation's own consumer number. Wheeling is to other premises.").format(
						row.preference_order
					)
				)
			if row.preference_order in seen:
				frappe.throw(_("Duplicate preference order {0}.").format(row.preference_order))
			seen.add(row.preference_order)

	def before_submit(self):
		if not self.spin:
			frappe.throw(
				_("The Solar Plant Identification Number (SPIN) is allotted by the DISCOM on execution "
				  "and is the identifier every later document uses. Record it before submitting."),
				title=_("SPIN Required"),
			)

	def on_submit(self):
		frappe.db.set_value("Solar Installation", self.solar_installation, "spin", self.spin, update_modified=False)
		frappe.db.set_value("Solar Consumer", self.solar_consumer, "spin", self.spin, update_modified=False)
		self.advance_stage()
		try:
			documents.generate_document(self.solar_installation, "KSEB-NETMETER-AGREEMENT")
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: agreement for {self.name}")

	def advance_stage(self):
		status = frappe.db.get_value(
			"Installation Stage Log", {"parent": self.solar_installation, "stage_code": "AGMT"}, "status"
		)
		if status in (None, "Completed", "Skipped"):
			return
		try:
			stages.advance_stage(
				self.solar_installation, "AGMT", actual_date=self.agreement_date, external_reference=self.spin
			)
		except frappe.ValidationError as exc:
			frappe.msgprint(_("AGMT stage not advanced: {0}").format(exc), indicator="orange")


@frappe.whitelist()
def terminate(agreement, terminated_by, reason):
	"""Either party may terminate on thirty days' notice. Record it; never delete."""
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when terminating an agreement."))
	doc = frappe.get_doc("Net Metering Agreement", agreement)
	doc.check_permission("write")
	doc.db_set("is_terminated", 1, update_modified=False)
	doc.db_set("terminated_on", frappe.utils.today(), update_modified=False)
	doc.db_set("terminated_by", terminated_by, update_modified=False)
	doc.db_set("termination_reason", reason.strip(), update_modified=False)
	doc.add_comment("Comment", _("Agreement terminated by {0}: {1}").format(terminated_by, reason.strip()))
	return True


def _address_text(address):
	if not address:
		return ""
	parts = [address.address_line1, address.address_line2, address.city, address.state, address.pincode]
	return ", ".join(str(p) for p in parts if p)
