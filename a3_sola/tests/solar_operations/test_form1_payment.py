# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 1 Payment is a confirmation: paid or not, a remark, the receipt on the task's
Documents - and, paid out of pocket, a reimbursement claim, as the stamp paper's is."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_crud, tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import task_row
from a3_sola.www.a3solaportal import collections


class TestForm1Payment(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()
		template = frappe.db.get_value("Solar Installation", self.installation.name, "stage_template")
		frappe.db.set_value("Installation Stage Template Detail", {"parent": template, "stage_code": "F1PAY"},
			"allow_reimbursement", 1)

	def pay(self, **values):
		made = portal_crud.create_record(slug="fee-payments", source_dt="Solar Installation", source=self.installation.name,
			source_task="F1PAY", **values)
		return frappe.get_doc("Statutory Fee Payment", made["name"])

	def test_the_form_asks_only_paid_claim_and_remark(self):
		target = tasks.open_task(self.installation.name, "F1PAY", create_draft=0)
		_doc, groups = collections.task_form_groups("fee-payments", dict(target["route_options"]))
		fields = [f["fieldname"] for g in groups for s in g["sections"] for f in s["fields"]]
		self.assertEqual(fields, ["payment_completed", "claim_reimbursement", "remarks"])

	def test_payment_completed_completes_the_task(self):
		doc = self.pay(payment_completed=1, remarks="Paid at the section office")
		self.assertEqual((doc.docstatus, doc.paid_by), (1, "Company on Behalf of Customer"))
		self.assertTrue(doc.form2_due_date)
		row, _inst = task_row(self.installation, "F1PAY")
		self.assertEqual(row.status, "Completed")
		self.assertFalse(doc.reimbursement)

	def test_not_paid_yet_leaves_it_open(self):
		doc = self.pay(remarks="Going tomorrow")
		self.assertEqual(doc.docstatus, 0)
		row, _inst = task_row(self.installation, "F1PAY")
		self.assertNotEqual(row.status, "Completed")

	def test_paid_out_of_pocket_is_claimed_back_once(self):
		doc = self.pay(payment_completed=1, claim_reimbursement=1)
		if not frappe.utils.flt(doc.amount_gross):
			self.skipTest("no application fee on this site's fee schedule")
		claim = frappe.get_doc("Expense Reimbursement", doc.reimbursement)
		self.assertEqual((claim.task_code, claim.amount, claim.status), ("F1PAY", doc.amount_gross, "Pending Approval"))
		doc.reload()
		doc.save()
		self.assertEqual(frappe.db.count("Expense Reimbursement", {"source_document": doc.name}), 1)
