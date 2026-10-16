# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Material Dispatch is recorded on its own page: the date, vehicle, driver and serials."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from a3_sola.api import dispatch_task
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestDispatchTask(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation().name
		self.tag = frappe.generate_hash(length=6).upper()

	def row(self):
		return next(r for r in frappe.get_doc("Solar Installation", self.job).stages if r.stage_code == "DISP")

	def test_saving_records_the_details_and_serials(self):
		state = dispatch_task.save(self.job, dispatch_date=today(), dispatch_vehicle="KL-07-AB-1234",
			module_serials=f"M1{self.tag}\nM2{self.tag}\nM2{self.tag}", inverter_serials=f"I1{self.tag}")
		self.assertEqual(state["serials"]["Module"], [f"M1{self.tag}", f"M2{self.tag}"])
		self.assertEqual(state["serials"]["Inverter"], [f"I1{self.tag}"])
		self.assertEqual(state["dispatch"]["dispatch_vehicle"], "KL-07-AB-1234")
		self.assertEqual(self.row().status, "In Progress")

	def test_dispatch_needs_a_date_not_in_the_future(self):
		with self.assertRaises(frappe.ValidationError):
			dispatch_task.mark_dispatched(self.job)
		with self.assertRaises(frappe.ValidationError):
			dispatch_task.save(self.job, dispatch_date=add_days(today(), 3))

	def test_mark_dispatched_completes_the_task(self):
		state = dispatch_task.mark_dispatched(self.job, dispatch_date=today())
		self.assertEqual(state["task"]["status"], "Completed")
		self.assertEqual(str(self.row().actual_completion_date), today())
