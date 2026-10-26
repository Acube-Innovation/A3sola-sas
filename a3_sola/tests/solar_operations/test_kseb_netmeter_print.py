# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The net meter request for the Form 3 Submission prints from the job as the team's Word file
lays it out, to view or download - the task's row Generated, with no upload."""

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import documents, kseb_netmeter_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.www.a3solaportal import collections


class TestKSEBNetMeterPrint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def test_the_letter_is_the_jobs(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		f = kseb_netmeter_print.context(inst)
		self.assertEqual(f.consumer_number, inst.consumer_number)
		# The category is the tariff - the customer's, else the job's - and the phase.
		tariff = frappe.db.get_value("Solar Consumer", inst.solar_consumer, "tariff_category") or inst.tariff_category
		self.assertEqual(f.category.split("/")[0], tariff or "")
		self.assertIn(f.phase, ("Single Phase", "Three Phase"))
		self.assertTrue(f.capacity.endswith("kWp"))

	def test_it_prints_on_one_page(self):
		name, pdf = kseb_netmeter_print.render(self.installation.name)
		self.assertEqual(len(PdfReader(BytesIO(pdf)).pages), 1)
		self.assertTrue(name.endswith(" - Request for Allocation of Bidirectional Meter.pdf"))  # the customer first
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		html = " ".join(kseb_netmeter_print.html(inst).split())
		self.assertIn("<b>Sub: -</b> Request for allocation of Bi-directional Meter", html)
		self.assertIn(f"<b>Consumer No. {self.installation.consumer_number}</b>", html)

	def test_the_task_offers_view_and_download_and_takes_no_upload(self):
		links = portal_tasks._prints(frappe._dict(stage_code="KFORMS"), self.installation.name)[kseb_netmeter_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Net Meter Request", "Download Net Meter Request"])
		self.assertFalse(any(p.get("keep_file") for p in links))  # Generated: no upload
		page = [d["label"] for d in collections.task_downloads(self.installation.name, "KFORMS")]
		self.assertIn("Download Net Meter Request", page)

	def test_generating_the_template_attaches_this_print(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Request</p>")
		with patch.object(kseb_netmeter_print, "render", return_value=("Request.pdf", pdf)) as render:
			result = documents.generate_document(self.installation.name, kseb_netmeter_print.CODE)
		render.assert_called_once()
		self.assertEqual(frappe.get_doc("File", {"file_url": result["file_url"]}).get_content(), pdf)
