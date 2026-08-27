# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Commissioning, and the DISCOM's pre-energisation checklist.

Two gates here protect the client's registration rather than their paperwork:

* Earthing and surge protection are exactly the defect categories the ministry's vendor
  violation SOP lists. A missing record is what gets a vendor deactivated.
* The consumer-vendor agreement requires a performance ratio of at least 75% at
  commissioning, measured with a NABL-calibrated radiation sensor, and maintained for five
  years. It is a clause in a signed agreement, not a chart.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_years, flt, getdate

from a3_sola.api import calculations, documents, materials, stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_float, get_value

LINKS = (("solar_installation", "Solar Installation"), ("solar_consumer", "Solar Consumer"))

PROTECTION_FUNCTIONS = [
	("Over Voltage Trip", "V"),
	("Under Voltage Trip", "V"),
	("Over Frequency Trip", "Hz"),
	("Under Frequency Trip", "Hz"),
	("Anti-Islanding", ""),
	("Grid Failure Trip Delay", "s"),
	("Re-Energisation Delay", "s"),
]


class CommissioningReport(Document):
	def autoname(self):
		set_name(self, "commissioning_series_prefix", ".YYYY.-.#####", fallback="SOL-COM")

	def before_insert(self):
		self.seed_protection_settings()

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_one_per_installation()
		self.seed_protection_settings()
		self.pull_checklist_context()
		self.compute_tests()
		self.compute_performance_ratio()
		self.check_open_snags()

	def validate_one_per_installation(self):
		existing = frappe.db.get_value(
			"Commissioning Report",
			{"solar_installation": self.solar_installation, "name": ["!=", self.name], "docstatus": ["<", 2]},
			"name",
		)
		if existing:
			frappe.throw(
				_("Installation {0} already has commissioning report {1}.").format(
					self.solar_installation, frappe.utils.get_link_to_form("Commissioning Report", existing)
				)
			)

	def seed_protection_settings(self):
		if self.protection_settings:
			return
		for function, unit in PROTECTION_FUNCTIONS:
			self.append(
				"protection_settings",
				{"protection_function": function, "is_provided": 1, "setting_unit": unit or None},
			)

	def pull_checklist_context(self):
		"""Everything the DISCOM's checklist asks for, fetched - never transcribed."""
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		consumer = frappe.get_cached_doc("Solar Consumer", installation.solar_consumer)
		section = (
			frappe.get_cached_doc("DISCOM Section", installation.discom_section)
			if installation.discom_section
			else None
		)
		company = frappe.get_cached_doc("Company", self.company)
		address = (
			frappe.get_cached_doc("Address", consumer.installation_address)
			if consumer.installation_address
			else None
		)

		self.electrical_division = section.electrical_division if section else None
		self.electrical_subdivision = section.electrical_subdivision if section else None
		self.electrical_section = section.section_name if section else None
		self.consumer_number = consumer.consumer_number
		self.tariff_category = consumer.tariff_category
		self.connected_load_watts = consumer.connected_load_watts
		self.plant_owner_name = consumer.consumer_name
		self.installation_address = _address_text(address)
		self.consumer_email = consumer.email_id
		self.consumer_contact_no = consumer.mobile_no
		self.alternate_contact_no = consumer.alternate_contact_no
		self.consumer_bank_name = consumer.bank_name
		self.consumer_bank_account_no = consumer.bank_account_no
		self.consumer_bank_ifsc = consumer.bank_ifsc_code

		self.installer_name = company.epc_name or company.company_name
		self.installer_address = company.epc_address
		self.installer_email = company.epc_email
		self.installer_contact_no = company.epc_contact_no

		if not self.total_capacity_kwp:
			self.total_capacity_kwp = installation.capacity_kw
		if not self.module_count:
			self.module_count = installation.module_count
		if not self.module_wattage:
			self.module_wattage = installation.module_wattage
		if not self.module_make and installation.module_make:
			self.module_make = frappe.db.get_value("Component Make", installation.module_make, "make_name")
		if not self.inverter_make and installation.inverter_make:
			self.inverter_make = frappe.db.get_value("Component Make", installation.inverter_make, "make_name")
		if not self.inverter_capacity_kw:
			self.inverter_capacity_kw = installation.inverter_capacity_kw
		if not self.inverter_phase:
			self.inverter_phase = installation.connection_type
		if not self.inverter_serial_no:
			inverter = next((r for r in installation.serials if r.component_type == "Inverter"), None)
			self.inverter_serial_no = inverter.serial_no if inverter else None
		self.plant_type = {"On-Grid": "On Grid", "Off-Grid": "Off Grid", "Hybrid": "Hybrid"}.get(
			installation.system_type, self.plant_type or "On Grid"
		)

	def compute_tests(self):
		readings = [r for r in self.test_readings if r.measured_value]
		self.all_tests_passed = 1 if readings and all(r.is_within_limit for r in readings) else 0

	def compute_performance_ratio(self):
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		generation = calculations.estimate_generation(installation.capacity_kw)
		self.expected_daily_generation_kwh = generation["daily_generation_kwh"]
		self.performance_ratio_threshold = get_float("performance_ratio_threshold_percent", 75.0)
		if flt(self.first_day_generation_kwh) and flt(self.expected_daily_generation_kwh):
			self.performance_ratio_at_commissioning = flt(
				flt(self.first_day_generation_kwh) * 100.0 / flt(self.expected_daily_generation_kwh), 2
			)
		else:
			self.performance_ratio_at_commissioning = 0

	def check_open_snags(self):
		self.has_open_snags = 1 if frappe.db.count(
			"Installation Snag",
			{
				"solar_installation": self.solar_installation,
				"status": ["in", ["Open", "In Progress"]],
				"docstatus": ["<", 2],
			},
		) else 0

	# ------------------------------------------------------------------- gates
	def before_submit(self):
		self.gate_safety_records()
		self.gate_protection_settings()
		self.gate_performance_ratio()

	def gate_safety_records(self):
		missing = []
		if not self.earthing_verified:
			missing.append(_("earthing verification"))
		if not self.surge_protection_installed:
			missing.append(_("surge protection record"))
		if not self.commissioning_certificate_no:
			missing.append(_("commissioning certificate number"))
		if not self.commissioning_certificate:
			missing.append(_("commissioning certificate attachment"))
		if missing:
			frappe.throw(
				_("Commissioning cannot be submitted without {0}. These are exactly the defect "
				  "categories the ministry's vendor violation SOP lists.").format(", ".join(missing)),
				title=_("Commissioning Gate"),
			)

	def gate_protection_settings(self):
		"""What the Assistant Engineer refuses on. A rejection costs another site visit."""
		gaps = []
		for row in self.protection_settings:
			if not row.is_provided:
				gaps.append(_("{0}: not provided").format(row.protection_function))
			elif not row.setting_value and row.protection_function != "Anti-Islanding":
				gaps.append(_("{0}: no setting recorded").format(row.protection_function))
			elif not (row.proof_type and row.proof_attachment):
				gaps.append(_("{0}: no documentary proof").format(row.protection_function))
		if gaps:
			frappe.throw(
				_("The DISCOM inspects every inverter protection setting and asks for proof of each. "
				  "Outstanding:<br>- {0}").format("<br>- ".join(gaps)),
				title=_("Protection Settings Incomplete"),
			)

	def gate_performance_ratio(self):
		"""75% at commissioning, measured with a valid calibration, per the vendor agreement."""
		threshold = flt(self.performance_ratio_threshold) or get_float(
			"performance_ratio_threshold_percent", 75.0
		)
		if not frappe.db.get_value("Solar Installation", self.solar_installation, "subsidy_scheme"):
			return

		if not self.radiation_sensor_calibration_certificate or not self.calibration_valid_until:
			frappe.throw(
				_("The performance ratio must be measured with a radiation sensor carrying a valid "
				  "calibration certificate. Record the certificate and its validity."),
				title=_("Calibration Required"),
			)
		if getdate(self.calibration_valid_until) < getdate(self.commissioning_date):
			frappe.throw(
				_("The radiation sensor's calibration expired on {0}, before the commissioning date {1}.").format(
					self.calibration_valid_until, self.commissioning_date
				),
				title=_("Calibration Expired"),
			)
		if flt(self.performance_ratio_at_commissioning) < threshold:
			if not (self.pr_override_reason or "").strip():
				frappe.throw(
					_("Performance ratio is {0}% against a contractual floor of {1}%. The consumer-vendor "
					  "agreement requires {1}% at commissioning. Record a reason to proceed.").format(
						flt(self.performance_ratio_at_commissioning), threshold
					),
					title=_("Below the Contractual Performance Ratio"),
				)
			if not set(frappe.get_roles()).intersection(stages.MANAGER_ROLES):
				frappe.throw(
					_("Only an operations manager may commission below the contractual performance ratio."),
					frappe.PermissionError,
				)

	# ------------------------------------------------------------------ on submit
	def on_submit(self):
		self.write_warranty_window()
		self.advance_stage()
		self.generate_documents()
		if flt(self.performance_ratio_at_commissioning) < flt(self.performance_ratio_threshold):
			self.add_comment(
				"Comment",
				_("Commissioned below the contractual performance ratio ({0}% against {1}%): {2}").format(
					flt(self.performance_ratio_at_commissioning),
					flt(self.performance_ratio_threshold),
					self.pr_override_reason,
				),
			)
		materials.check_variance(frappe.get_doc("Solar Installation", self.solar_installation))
		# PHASE 3 CONTRACT: project creation and the five-year O&M contract register here.
		stages.on_commissioning_submitted(self)

	def write_warranty_window(self):
		"""Phase 3 consumes these two dates plus the package and the serial register."""
		years = 5
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		if installation.solar_package:
			years = int(
				frappe.db.get_value("Solar Package", installation.solar_package, "warranty_years") or 5
			)
		frappe.db.set_value(
			"Solar Installation",
			self.solar_installation,
			{
				"warranty_start_date": self.commissioning_date,
				"warranty_end_date": add_years(getdate(self.commissioning_date), years),
				"performance_ratio_at_commissioning": self.performance_ratio_at_commissioning,
			},
			update_modified=False,
		)

	def advance_stage(self):
		status = frappe.db.get_value(
			"Installation Stage Log", {"parent": self.solar_installation, "stage_code": "COMM"}, "status"
		)
		if status in (None, "Completed", "Skipped"):
			return
		try:
			stages.advance_stage(
				self.solar_installation,
				"COMM",
				actual_date=self.commissioning_date,
				external_reference=self.commissioning_certificate_no,
			)
		except frappe.ValidationError as exc:
			frappe.msgprint(_("COMM stage not advanced: {0}").format(exc), indicator="orange")

	def generate_documents(self):
		"""The DISCOM checklist stops being a spreadsheet."""
		for code in ("KSEB-TESTING-CHECKLIST", "CUST-COMMISSIONING-CERTIFICATE", "CUST-HANDOVER-PACK"):
			try:
				documents.generate_document(self.solar_installation, code)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"a3_sola: commissioning docs for {self.name}")


def _address_text(address):
	if not address:
		return ""
	parts = [address.address_line1, address.address_line2, address.city, address.state, address.pincode]
	return ", ".join(str(p) for p in parts if p)
