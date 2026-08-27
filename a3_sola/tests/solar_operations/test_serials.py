# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Serial traceability - compliance, not bookkeeping."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import serials
from a3_sola.tests.solar_operations.fixtures import capture_serials, make_installation


class TestSerialUniqueness(FrappeTestCase):
	def test_duplicate_within_one_installation_rejected(self):
		installation = make_installation()
		doc = frappe.get_doc("Solar Installation", installation.name)
		for _ in range(2):
			doc.append("serials", {"component_type": "Module", "serial_no": "DUP-001"})
		doc.flags.ignore_validate_update_after_submit = True
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.save(ignore_permissions=True)
		self.assertIn("twice", str(ctx.exception))

	def test_duplicate_across_installations_names_the_first(self):
		"""The ministry rejects portal submissions containing a repeated serial."""
		first = make_installation()
		capture_serials(first, modules=2, inverters=1)
		shared = frappe.get_doc("Solar Installation", first.name).serials[0].serial_no

		second = make_installation()
		doc = frappe.get_doc("Solar Installation", second.name)
		doc.append("serials", {"component_type": "Module", "serial_no": shared})
		doc.flags.ignore_validate_update_after_submit = True
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.save(ignore_permissions=True)
		self.assertIn(first.name, str(ctx.exception))

	def test_capture_counts_and_completeness(self):
		installation = make_installation()
		doc = capture_serials(installation, modules=6, inverters=1)
		self.assertEqual(doc.modules_captured, 6)
		self.assertEqual(doc.inverters_captured, 1)
		self.assertEqual(doc.modules_expected, 6)
		self.assertEqual(doc.serial_capture_complete, 1)

	def test_incomplete_capture_is_flagged(self):
		installation = make_installation()
		doc = capture_serials(installation, modules=3, inverters=1)
		self.assertEqual(doc.serial_capture_complete, 0)

	def test_manifest_carries_the_audit_columns(self):
		installation = make_installation()
		capture_serials(installation, modules=6, inverters=1)
		csv_text = serials.export_serial_manifest(installation.name)
		header = csv_text.splitlines()[0]
		for column in ("Consumer Number", "Serial Number", "DCR Certificate", "Capacity kW"):
			self.assertIn(column, header)
		self.assertEqual(len(csv_text.strip().splitlines()), 8)  # header + 7 serials

	def test_completion_report_data_matches_the_register(self):
		"""Both completion reports render from this, so they cannot disagree."""
		installation = make_installation()
		capture_serials(installation, modules=6, inverters=1)
		data = serials.get_completion_report_data(installation.name)
		self.assertEqual(len(data["module_serial_numbers"]), 6)
		self.assertEqual(data["module_count"], 6)
		self.assertTrue(data["inverter_serial_number"])
		self.assertEqual(data["consumer_number"], installation.consumer_number)
