# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Enter Serial Numbers task: a job's serials from its supplier's bill, read off a photo of
the labels, or typed - onto the one register (api/serial_entry)."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import serial_entry


class TestSerialReading(FrappeTestCase):
	def test_a_bill_line_is_typed_by_its_hsn_code_then_its_name(self):
		self.assertEqual(serial_entry.kind_of("85414300", "RENEWSYS DESERV 565WP"), "Module")
		self.assertEqual(serial_entry.kind_of("85049090", "POLYCAB SOLAR GRID TIE INVERTER"), "Inverter")
		self.assertEqual(serial_entry.kind_of("", "SolarEdge Power Optimiser S440"), "Optimiser")
		self.assertEqual(serial_entry.kind_of("90283010", "L&T Unidirectional meter"), "Other")

	def test_only_serials_are_read_off_a_label(self):
		text = """RENEWSYS DESERV 565WP  85414300  5 %  6 Nos  12,599.50  75,597.00
			r1200042260127725   R1200042260127951
			3K0070926-2630-098203585P   Dated 29-Oct-26   GSTIN/UIN: 32AAJCR8845G1Z4
			Invoice RPVT/26-27/6602   Copper Bonded Rod 14x1220mmx100microns   Ph 9746620666
			UDYAM-KL-02-0016757   2026091910"""
		self.assertEqual(serial_entry.serial_tokens(text), ["r1200042260127725", "R1200042260127951",
			"3K0070926-2630-098203585P", "9746620666", "2026091910"])


class TestSerialRegister(FrappeTestCase):
	"""On a job with the task: the register written and checked as the page saves it."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.job = frappe.db.get_value("Installation Stage Log", {"stage_code": serial_entry.CODE,
			"parenttype": "Solar Installation"}, "parent")
		if not self.job:
			raise unittest.SkipTest("No job with an Enter Serial Numbers task.")

	def tearDown(self):
		frappe.db.rollback()

	def test_the_register_is_saved_by_type(self):
		s = serial_entry.save(self.job, module_serials="TESTMOD0000001\nTESTMOD0000002", inverter_serials="TESTINV0000001",
			optimiser_serials="", other_serials="")
		self.assertEqual(s["register"]["Module"], ["TESTMOD0000001", "TESTMOD0000002"])
		self.assertEqual(s["register"]["Inverter"], ["TESTINV0000001"])
		self.assertEqual(s["task"]["status"] in ("In Progress", "Completed"), True)

	def test_a_serial_twice_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			serial_entry.save(self.job, module_serials="TESTMOD0000001", inverter_serials="", optimiser_serials="",
				other_serials="TESTMOD0000001")

	def test_done_waits_for_every_module(self):
		inst = frappe.get_doc("Solar Installation", self.job)
		if not int(inst.get("modules_expected") or inst.get("module_count") or 0):
			raise unittest.SkipTest("The job expects no module count.")
		row = next(r for r in inst.stages if r.stage_code == serial_entry.CODE)
		frappe.db.set_value(row.doctype, row.name, "status", "In Progress")
		serial_entry.save(self.job, module_serials="TESTMOD0000001", inverter_serials="", optimiser_serials="", other_serials="")
		with self.assertRaises(frappe.ValidationError):
			serial_entry.mark_done(self.job)
