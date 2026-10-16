# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A work order carries the job to its contractor: customer, site, system, material and
photographs - on its pages and in the PDF it is sent as."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import portal_share, work_order_print
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_contractor_and_work_orders import make_contractor
from a3_sola.tests.solar_operations.test_tasks import make_work_order


class TestWorkOrderPrint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation()
		self.contractor = make_contractor(company=self.job.company, mobile_no="9000033333")

	def order(self, work_type):
		return make_work_order(self.job, work_type, solar_contractor=self.contractor.name,
			work_description="Mind the east parapet.")

	def test_the_job_is_on_the_order(self):
		ctx = work_order_print.job_context(self.job.name, None, work_order=self.order("Structure Erection"))
		self.assertEqual(ctx.kind, "Structure")
		self.assertEqual(ctx.contractor.name, self.contractor.name)
		self.assertTrue(ctx.customer["name"])
		self.assertIn("Capacity", [label for label, _v in ctx.system])

	def test_the_pdf_carries_the_job_for_each_kind(self):
		consumer = frappe.db.get_value("Solar Installation", self.job.name, "consumer_name")
		for work_type, title in (("Structure Erection", "WORK ORDER - STRUCTURE"), ("Module Mounting", "WORK ORDER - INSTALLATION")):
			order = self.order(work_type)
			text = " ".join(PdfReader(BytesIO(work_order_print.render(order)[1])).pages[0].extract_text().split())
			for expected in (title, consumer, self.contractor.contractor_name, "Mind the east parapet."):
				self.assertIn(expected, text)

	def test_it_is_sent_to_its_contractor(self):
		order = self.order("Module Mounting")
		links = portal_share.share_links(order, work_order_print.url(order.name))
		self.assertEqual(links["whatsapp_to"], "9000033333")
		self.assertIn(order.name, links["subject"])
		frappe.local.request_ip = "127.0.0.1"
		with self.assertRaises(frappe.PermissionError):
			portal_share.shared_pdf("Installation Work Order", order.name, "not-the-key")

	def test_an_installation_order_carries_the_single_line_diagram(self):
		from a3_sola.api import documents

		order = self.order("Module Mounting")
		before = len(PdfReader(BytesIO(work_order_print.render(order)[1])).pages)
		sld = frappe.get_doc({"doctype": "File", "file_name": "sld.pdf", "is_private": 1,
			"content": documents.plain_pdf("<h1>SLD TEST DIAGRAM</h1>"),
			"attached_to_doctype": "Solar Installation", "attached_to_name": self.job.name}).insert(ignore_permissions=True)
		documents.register_document(frappe.get_doc("Solar Installation", self.job.name), "DSGN", "Solar Installation",
			self.job.name, work_order_print.SLD, sld.file_url, kind="Uploaded")
		reader = PdfReader(BytesIO(work_order_print.render(frappe.get_doc("Installation Work Order", order.name))[1]))
		self.assertEqual(len(reader.pages), before + 1)
		self.assertIn("SLD TEST DIAGRAM", " ".join(reader.pages[-1].extract_text().split()))
		# A structure order goes without it.
		self.assertIsNone(work_order_print.job_context(self.job.name, "Structure").sld)
