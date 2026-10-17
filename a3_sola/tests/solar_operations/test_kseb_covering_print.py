# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The covering letter for the Form 3 Submission prints from the job as the team's Word file
lays it out, to view or download - the task's row Generated, with no upload."""

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import documents, kseb_covering_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.www.a3solaportal import collections


class TestKSEBCoveringPrint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def job(self):
		return frappe.get_doc("Solar Installation", self.installation.name)

	def test_the_letter_is_the_jobs(self):
		inst = self.job()
		inst.set("panels", [])
		inst.append("panels", {"panel_capacity_wp": 550, "nos": 10})
		f = kseb_covering_print.context(inst)
		self.assertEqual(f.capacity, "5.5kWp")
		self.assertEqual(f.consumer_number, inst.consumer_number)
		self.assertEqual(f.name, inst.consumer_name)
		self.assertEqual(f.section, frappe.db.get_value("DISCOM Section", inst.discom_section, "section_name"))

	def test_it_prints_on_one_page_with_what_is_enclosed(self):
		name, pdf = kseb_covering_print.render(self.installation.name)
		self.assertEqual(len(PdfReader(BytesIO(pdf)).pages), 1)
		self.assertTrue(name.startswith("Covering Letter to the Assistant Engineer - "))
		html = " ".join(kseb_covering_print.html(self.job()).split())
		for expected in (f"<b>Consumer No. {self.installation.consumer_number}</b>", "<b>Annexure 2</b> signed",
				"Installation Checklist", "Solar Agreement on Stamp Paper signed", '"Letter Antiqua"'):
			self.assertIn(expected, html)
		# Bold only where the Word file has it: not the subject, not the address.
		self.assertIn("<b>Sub: -</b> Submission of Documents", html)

	def test_the_task_offers_view_and_download_and_takes_no_upload(self):
		links = portal_tasks._prints(frappe._dict(stage_code="KFORMS"), self.installation.name)[kseb_covering_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Covering Letter", "Download Covering Letter"])
		self.assertFalse(any(p.get("keep_file") for p in links))  # Generated: no upload
		self.assertTrue(links[1]["url"].endswith("&download=1"))
		page = [d["label"] for d in collections.task_downloads(self.installation.name, "KFORMS")]
		self.assertIn("Download Covering Letter", page)

	def test_generating_the_template_attaches_this_print(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Letter</p>")
		with patch.object(kseb_covering_print, "render", return_value=("Letter.pdf", pdf)) as render:
			result = documents.generate_document(self.installation.name, kseb_covering_print.CODE)
		render.assert_called_once()
		self.assertEqual(frappe.get_doc("File", {"file_url": result["file_url"]}).get_content(), pdf)
