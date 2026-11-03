# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Tasks start together on the payment dates, each due its SLA later (seed_stages): Meter
Purchase takes 15 days when its meter is bought from KSEB, 3 otherwise, and the serials and
the payment after installation start the day the task before them is done, due a day later."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from a3_sola.api import stages
from a3_sola.setup import seed_stages
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestPaymentTaskFlow(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.inst = make_installation()

	def tearDown(self):
		frappe.db.rollback()

	def row(self, code):
		return next(r for r in self.inst.stages if r.stage_code == code)

	def save(self):
		self.inst.flags.ignore_validate_update_after_submit = True
		self.inst.save(ignore_permissions=True)

	def test_the_slas_are_the_agreed_ones(self):
		expected = {"NPA": 1, "ACPT": 1, "FRM1": 1, "F1PAY": 2, "STMP": 2, "DSGN": 3, "SDSGN": 3, "LOAN": 3,
			"SPROC": 1, "PROC": 1, "DISP": 2, "IWOS": 4, "IWOI": 5, "SUPINV": 2, "FRM2": 1, "F2PAY": 2,
			"SERIAL": 1, "MATL": 1, "BAL": 1, "KFORMS": 5, "COMM": 3, "DBT": 3}
		seeded = {t["code"]: t["sla_days"] for t in seed_stages.TASKS}
		self.assertEqual({c: seeded[c] for c in expected}, expected)

	def test_a_meter_bought_from_kseb_takes_fifteen_days(self):
		mtr = self.row("MTR")
		if mtr.status == "Skipped":
			self.skipTest("Meter Purchase is skipped on this job.")
		task = frappe.get_doc({"doctype": "Installation Task", "solar_installation": self.inst.name, "task_code": "MTR",
			"meter_source": "Vendor"})
		task.flags.ignore_mandatory = True
		task.db_insert()
		mtr.task_doctype, mtr.task_document = "Installation Task", task.name
		mtr.status, mtr.actual_start_date, mtr.due_date = "In Progress", today(), None
		self.save()
		self.assertEqual((self.row("MTR").sla_days, str(self.row("MTR").due_date)), (3, add_days(today(), 3)))
		frappe.db.set_value("Installation Task", task.name, "meter_source", "KSEB")
		self.save()
		self.assertEqual((self.row("MTR").sla_days, str(self.row("MTR").due_date)), (15, add_days(today(), 15)))

	def test_the_serials_and_the_balance_start_a_day_before_they_are_due(self):
		stages.exempt_half_payment(self.inst.name, "Test")
		self.inst.reload()
		for before, after in seed_stages.NEXT_AT_HALF.items():
			prior = self.row(after[0])
			prior.status, prior.actual_completion_date = "Completed", today()
			started = stages.start_next(self.inst, after[0])
			self.assertIn(before, [r.stage_code for r in started])
		self.save()
		for code in seed_stages.NEXT_AT_HALF:
			self.assertEqual(str(self.row(code).actual_start_date), today())
			self.assertEqual(str(self.row(code).due_date), add_days(today(), 1))
