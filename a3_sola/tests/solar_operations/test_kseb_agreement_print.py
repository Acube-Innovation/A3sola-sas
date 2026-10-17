# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The KSEB Solar Agreement prints from the job as the team's Word file lays it out - the
agreement's own answers where it has them, dotted lines where it is still to say - to view or
download from the Form 3 Submission task, whose row of that name is Generated, with no upload."""

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import agreement as agreement_api
from a3_sola.api import documents, kseb_agreement_print, portal_tasks
from a3_sola.patches.v1_2 import kseb_solar_agreement_name
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_agreement import execute
from a3_sola.www.a3solaportal import collections


def text_of(pdf):
	return [" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(pdf)).pages]


class TestKSEBAgreementPrint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def job(self):
		return frappe.get_doc("Solar Installation", self.installation.name)

	def test_without_an_agreement_it_prints_from_the_job(self):
		inst = self.job()
		doc, body = kseb_agreement_print.context(inst)
		self.assertTrue(doc.is_new())
		self.assertEqual(doc.consumer_name, inst.consumer_name)
		self.assertIn(inst.consumer_number, doc.consumer_number_and_category)
		self.assertIn(agreement_api.BLANK, body)  # the date, the officer, the SPIN
		self.assertFalse(frappe.db.exists("Solar Agreement", {"solar_installation": inst.name}))

	def test_the_capacity_is_the_panels_kwp_unless_typed(self):
		inst = self.job()
		inst.set("panels", [])
		inst.append("panels", {"panel_capacity_wp": 550, "nos": 10})
		self.assertEqual(kseb_agreement_print.context(inst)[0].plant_capacity_kwp, 5.5)
		agreement = execute(inst)
		frappe.db.set_value("Solar Agreement", agreement.name, "plant_capacity_kwp", 4.2)
		self.assertEqual(kseb_agreement_print.context(inst)[0].plant_capacity_kwp, 4.2)

	def test_an_executed_agreement_prints_its_answers(self):
		agreement = execute(self.installation, spin="SPINPRINT0042")
		frappe.db.set_value("Solar Agreement", agreement.name, {"first_party_witness_1": "Witness Alpha"})
		pages = text_of(kseb_agreement_print.render(self.installation.name)[1])
		text = " ".join(pages)
		self.assertIn("SPINPRINT0042", text)
		self.assertIn("Witness Alpha", text)
		self.assertIn("Agreement for Connecting Solar Energy System", text)
		# The last clause, and the schedule starting a page of its own.
		self.assertIn("average pooled purchase cost", text)
		schedule = next(i for i, p in enumerate(pages) if "SCHEDULE to Solar Net Metering Agreement" in p)
		self.assertTrue(pages[schedule].startswith("SCHEDULE to Solar Net Metering Agreement"))
		self.assertIn("Preference 3", pages[schedule])

	def test_the_task_offers_view_and_download_and_takes_no_upload(self):
		prints = portal_tasks._prints(frappe._dict(stage_code="KFORMS"), self.installation.name)
		links = prints[kseb_agreement_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View KSEB Solar Agreement", "Download KSEB Solar Agreement"])
		self.assertFalse(any(p.get("keep_file") for p in links))  # Generated: no upload
		self.assertTrue(links[1]["url"].endswith("&download=1"))
		page = [d["label"] for d in collections.task_downloads(self.installation.name, "KFORMS")]
		self.assertIn("Download KSEB Solar Agreement", page)

	def test_generating_the_template_attaches_this_print(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Agreement</p>")
		with patch.object(kseb_agreement_print, "render", return_value=("KSEB Solar Agreement.pdf", pdf)) as render:
			result = documents.generate_document(self.installation.name, kseb_agreement_print.CODE)
		render.assert_called_once()
		self.assertEqual(frappe.get_doc("File", {"file_url": result["file_url"]}).get_content(), pdf)

	def test_the_patch_renames_the_jobs_row(self):
		inst = self.job()
		row = next(r for r in inst.documents if r.solar_document_template and frappe.db.get_value(
			"Solar Document Template", r.solar_document_template, "template_code") == kseb_agreement_print.CODE)
		self.assertEqual(row.document_name, "KSEB Solar Agreement")
		frappe.db.set_value("Installation Document", row.name, "document_name", "Net metering agreement")
		kseb_solar_agreement_name.execute()
		self.assertEqual(frappe.db.get_value("Installation Document", row.name, "document_name"), "KSEB Solar Agreement")
