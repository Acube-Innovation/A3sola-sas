# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Commissioning: the DISCOM checklist and the 75% performance gate."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_years, getdate, today

from a3_sola.tests.solar_operations.fixtures import capture_serials, make_installation

PROTECTION_VALUES = {
	"Over Voltage Trip": ("264", "V", "200 ms"),
	"Under Voltage Trip": ("192", "V", "200 ms"),
	"Over Frequency Trip": ("50.50", "Hz", "200 ms"),
	"Under Frequency Trip": ("47.50", "Hz", "200 ms"),
	"Anti-Islanding": ("Provided", "", ""),
	"Grid Failure Trip Delay": ("60", "s", ""),
	"Re-Energisation Delay": ("60", "s", ""),
}


def make_report(installation, complete=True, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Commissioning Report",
			"company": installation.company,
			"solar_installation": installation.name,
			"commissioning_date": today(),
			"net_meter_serial_no": "NM-" + frappe.generate_hash(length=6).upper(),
			"commissioning_certificate_no": "CC-" + frappe.generate_hash(length=6).upper(),
			"commissioning_certificate": "/files/cc.pdf",
			"earthing_verified": 1,
			"surge_protection_installed": 1,
			"first_day_generation_kwh": 13.0,
			"radiation_sensor_id": "SENSOR-01",
			"radiation_sensor_calibration_certificate": "/files/cal.pdf",
			"calibration_lab": "NABL Accredited",
			"calibration_valid_until": add_days(today(), 180),
			"dc_isolator_on_inverter_incoming": 1,
			"visual_isolator_before_connectivity_point": 1,
			"wiring_as_per_approved_scheme": 1,
			"earthing_provided_ac_db": 1,
			"earthing_provided_dc_db": 1,
			"earthing_provided_structure_and_panels": 1,
			"earthing_provided_la_and_inverter_body": 1,
			"earthing_provided_isolator": 1,
		}
	)
	doc.update(kwargs)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	if complete:
		for row in doc.protection_settings:
			value, unit, trip = PROTECTION_VALUES[row.protection_function]
			row.setting_value = value
			row.setting_unit = unit or None
			row.trip_time = trip or None
			row.proof_type = "OEM Factory Test Certificate"
			row.proof_attachment = "/files/proof.pdf"
		doc.save(ignore_permissions=True)
	return doc


class TestDISCOMChecklist(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		capture_serials(self.installation, modules=6, inverters=1)

	def test_administrative_block_is_fetched_not_typed(self):
		report = make_report(self.installation)
		self.assertEqual(report.consumer_number, self.installation.consumer_number)
		self.assertTrue(report.electrical_section)
		self.assertTrue(report.installer_name)
		self.assertTrue(report.plant_owner_name)

	def test_protection_table_seeded_with_all_seven_functions(self):
		report = make_report(self.installation, complete=False)
		functions = {r.protection_function for r in report.protection_settings}
		self.assertEqual(len(functions), 7)
		self.assertIn("Anti-Islanding", functions)
		self.assertIn("Re-Energisation Delay", functions)

	def test_submission_blocked_without_protection_proof(self):
		"""Exactly what the Assistant Engineer refuses on."""
		report = make_report(self.installation, complete=False)
		with self.assertRaises(frappe.ValidationError) as ctx:
			report.submit()
		self.assertIn("protection setting", str(ctx.exception).lower())

	def test_submission_blocked_without_earthing_record(self):
		report = make_report(self.installation, earthing_verified=0)
		with self.assertRaises(frappe.ValidationError) as ctx:
			report.submit()
		self.assertIn("earthing", str(ctx.exception).lower())

	def test_certificate_is_mandatory_at_entry(self):
		"""Enforced at field level, so the report cannot even be saved without it."""
		with self.assertRaises(frappe.MandatoryError):
			make_report(self.installation, commissioning_certificate=None)

	def test_submission_blocked_without_the_certificate_number(self):
		report = make_report(self.installation)
		report.commissioning_certificate_no = None
		with self.assertRaises(frappe.ValidationError) as ctx:
			report.submit()
		self.assertIn("certificate", str(ctx.exception).lower())


class TestPerformanceGate(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		capture_serials(self.installation, modules=6, inverters=1)

	def test_ratio_computed_against_the_design_expectation(self):
		report = make_report(self.installation)
		self.assertGreater(report.performance_ratio_at_commissioning, 0)
		self.assertEqual(report.performance_ratio_threshold, 75.0)

	def test_expired_calibration_blocks_submission(self):
		report = make_report(self.installation, calibration_valid_until=add_days(today(), -5))
		with self.assertRaises(frappe.ValidationError) as ctx:
			report.submit()
		self.assertIn("calibration", str(ctx.exception).lower())

	def test_missing_calibration_blocks_submission(self):
		report = make_report(
			self.installation, radiation_sensor_calibration_certificate=None, calibration_valid_until=None
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			report.submit()
		self.assertIn("calibration", str(ctx.exception).lower())

	def test_below_threshold_requires_a_recorded_reason(self):
		"""75% is a clause in a signed agreement, not a chart."""
		report = make_report(self.installation, first_day_generation_kwh=5.0)
		self.assertLess(report.performance_ratio_at_commissioning, 75)
		with self.assertRaises(frappe.ValidationError) as ctx:
			report.submit()
		self.assertIn("75", str(ctx.exception))

	def test_below_threshold_allowed_with_a_manager_reason(self):
		report = make_report(
			self.installation,
			first_day_generation_kwh=5.0,
			pr_override_reason="Overcast on the commissioning day; retest scheduled.",
		)
		report.submit()
		self.assertEqual(report.docstatus, 1)


class TestCommissioningOutcome(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		capture_serials(self.installation, modules=6, inverters=1)

	def test_warranty_window_written_for_phase_three(self):
		report = make_report(self.installation)
		report.submit()
		installation = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(getdate(installation.warranty_start_date), getdate(report.commissioning_date))
		self.assertEqual(
			getdate(installation.warranty_end_date), add_years(getdate(report.commissioning_date), 5)
		)

	def test_performance_ratio_carried_to_the_installation(self):
		report = make_report(self.installation)
		report.submit()
		installation = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(
			installation.performance_ratio_at_commissioning, report.performance_ratio_at_commissioning
		)

	def test_one_report_per_installation(self):
		make_report(self.installation)
		with self.assertRaises(frappe.ValidationError):
			make_report(self.installation)
