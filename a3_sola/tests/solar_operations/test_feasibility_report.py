# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 1 Generation records the section's feasibility report as a file - uploaded on the
task's form like a picture is - and no longer asks for the AE acknowledgement number."""

import io
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_crud
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.www.a3solaportal import collections


class Upload:
	def __init__(self, content, content_type, filename="report.pdf"):
		self.stream, self.content_type, self.filename = io.BytesIO(content), content_type, filename


class TestFeasibilityReport(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from frappe.utils.pdf import get_pdf

		cls.pdf = get_pdf("<p>Feasibility report</p>")

	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def form(self):
		values = collections.task_source("installation-tasks", self.installation.name, "FRM1")
		if values is None:
			self.skipTest("no Form 1 Generation task on this site's template")
		_doc, groups = collections.task_form_groups("installation-tasks", values)
		return {f["fieldname"]: f for g in groups for s in g["sections"] for f in s["fields"]}

	def test_the_form_asks_for_the_report_not_the_acknowledgement(self):
		fields = self.form()
		self.assertNotIn("ae_acknowledgement_no", fields)
		self.assertEqual((fields["feasibility_report"]["type"], fields["feasibility_report"]["input"]), ("Attach", "file"))
		self.assertFalse(frappe.get_meta("Installation Task").has_field("ae_acknowledgement_no"))

	def upload(self, fieldname, content, content_type, slug="installation-tasks"):
		with patch.object(frappe, "request", frappe._dict(files={"file": Upload(content, content_type)})):
			return portal_crud.upload_image(slug=slug, fieldname=fieldname)

	def test_a_pdf_report_uploads_and_saves_with_the_task(self):
		self.form()
		url = self.upload("feasibility_report", self.pdf, "application/pdf")["file_url"]
		self.assertTrue(url.startswith("/private/files/"))
		made = portal_crud.create_record(slug="installation-tasks", source_dt="Solar Installation",
			source=self.installation.name, source_task="FRM1", status="Pending", feasibility_report=url)
		self.assertEqual(frappe.db.get_value("Installation Task", made["name"], "feasibility_report"), url)

	def test_only_a_pdf_or_picture_is_taken(self):
		with self.assertRaises(frappe.ValidationError):
			self.upload("feasibility_report", b"MZ\x90\x00", "application/x-msdownload")

	def test_another_attach_field_is_still_not_a_portal_upload(self):
		with self.assertRaises(frappe.ValidationError):
			self.upload("bank_advice", self.pdf, "application/pdf")
