# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Accept Customer also prints the consumer-vendor agreement word for word as the team's
"05_PMSGY Vendor Agreement.docx", and the quotation in the RIM format once the job has one."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import loan_print, portal_tasks, vendor_agreement_print
from a3_sola.setup import seed_stages
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.www.a3solaportal import collections


class TestAcceptCustomerDocuments(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def test_the_task_lists_all_three(self):
		task = next(t for t in seed_stages.TASKS if t["code"] == "ACPT")
		self.assertEqual([d[2] for d in task["documents"]],
			["NET-METERING-AGREEMENT", loan_print.QUOTATION, vendor_agreement_print.CODE])

	def test_the_agreement_is_the_jobs_word_for_word(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		f = vendor_agreement_print.context(inst)
		self.assertEqual(f.name, inst.consumer_name)
		html = " ".join(vendor_agreement_print.html(inst).split())
		# assertTrue, not assertIn: a failure would print the embedded font.
		self.assertTrue("The First Party hereby undertakes to perform the following activities:" in html)
		self.assertTrue("<strong>Insurance:</strong> Any insurance cost pertaining" in html)
		self.assertTrue(f"The cost for the system shall be Rs. {f.cost} plus KSEB Charges and Net Meter Charges." in html)

	def test_it_prints_signed_or_not(self):
		name, pdf = vendor_agreement_print.render(self.installation.name)
		self.assertTrue(name.endswith(" - Consumer-Vendor Agreement.pdf"))
		text = " ".join(" ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages).split())
		self.assertIn("Performance Ratio (PR) of Plant must be 75%", text)
		self.assertTrue(vendor_agreement_print.render(self.installation.name, signed=False)[0].endswith("(unsigned).pdf"))
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertTrue(".a3s-sign { visibility: hidden; }" in vendor_agreement_print.html(inst, signed=False))

	def test_the_task_offers_the_agreement_and_the_quotation_once_there_is_one(self):
		frappe.db.set_value("Solar Installation", self.installation.name, "quotation", None)
		prints = portal_tasks._prints(frappe._dict(stage_code="ACPT"), self.installation.name)
		self.assertIn(vendor_agreement_print.CODE, prints)
		self.assertNotIn(loan_print.QUOTATION, prints)
		labels = [p["label"] for p in collections.task_downloads(self.installation.name, "ACPT")]
		self.assertIn("View Vendor Agreement", labels)
		self.assertNotIn("View Quotation (RIM)", labels)
