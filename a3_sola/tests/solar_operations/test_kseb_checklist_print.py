# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEB's testing checklist prints from the job for the Form 3 Submission, as the team's
CHECKLIST.xlsx lays it out: the installer's YES and the standard protection settings until the
job is commissioned, the Commissioning Report's own answers after - to view or download, the
task's row Generated, with no upload."""

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import documents, kseb_checklist_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import capture_serials, make_installation
from a3_sola.tests.solar_operations.test_commissioning import make_report
from a3_sola.www.a3solaportal import collections


class TestKSEBChecklistPrint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def job(self):
		return frappe.get_doc("Solar Installation", self.installation.name)

	def test_the_job_answers_the_details(self):
		capture_serials(self.installation, modules=6, inverters=1)
		inst = self.job()
		f = kseb_checklist_print.context(inst)
		self.assertEqual(f.consumer_number, inst.consumer_number)
		self.assertEqual(f.owner, inst.consumer_name)
		self.assertEqual(f.tariff, f.tariff.upper())
		self.assertTrue(f.installer)
		serial = next(r.serial_no for r in inst.serials if r.component_type == "Inverter")
		self.assertIn(serial, f.inverter)
		self.assertTrue(f.capacity.endswith("KWp"))

	def test_before_commissioning_the_installer_says_yes_and_the_settings_are_standard(self):
		f = kseb_checklist_print.context(self.job())
		self.assertEqual({f.dc_isolator, f.visual_isolator, f.wiring, f.earthing, f.completion_certificate}, {"YES"})
		self.assertEqual(f.dc_voltage, kseb_checklist_print.BLANK)
		self.assertEqual((f.settings.over_voltage, f.settings.under_voltage, f.settings.voltage_trip_time),
			("264 V", "192 V", "200 MS"))
		self.assertEqual((f.settings.over_frequency, f.settings.under_frequency), ("50.5 Hz", "47.5 Hz"))
		self.assertEqual(f.settings.grid_failure_delay, "60 SECONDS")

	def test_the_standard_settings_are_the_settings(self):
		frappe.db.set_single_value("A3 Sola Settings", "kseb_over_voltage_trip_v", 260)
		self.assertEqual(kseb_checklist_print.context(self.job()).settings.over_voltage, "260 V")

	def test_after_commissioning_the_report_answers(self):
		make_report(self.installation, dc_input_voltage=550, wiring_as_per_approved_scheme=0)
		f = kseb_checklist_print.context(self.job())
		self.assertEqual(f.dc_voltage, "550")
		self.assertEqual(f.wiring, "NO")
		self.assertEqual(f.settings.over_frequency, "50.50 Hz")
		self.assertEqual(f.settings.voltage_trip_time, "200 MS")

	def test_it_prints_on_two_pages(self):
		name, pdf = kseb_checklist_print.render(self.installation.name)
		reader = PdfReader(BytesIO(pdf))
		self.assertLessEqual(len(reader.pages), 2)
		self.assertIn(self.installation.consumer_number, reader.pages[0].extract_text())
		self.assertTrue(name.endswith(" - Installation and Inverter Testing Checklist.pdf"))  # the customer first

	def test_the_task_offers_view_and_download_and_takes_no_upload(self):
		links = portal_tasks._prints(frappe._dict(stage_code="KFORMS"), self.installation.name)[kseb_checklist_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Testing Checklist", "Download Testing Checklist"])
		self.assertFalse(any(p.get("keep_file") for p in links))  # Generated: no upload
		self.assertTrue(links[1]["url"].endswith("&download=1"))
		page = [d["label"] for d in collections.task_downloads(self.installation.name, "KFORMS")]
		self.assertIn("Download Testing Checklist", page)

	def test_generating_the_template_attaches_this_print(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Checklist</p>")
		with patch.object(kseb_checklist_print, "render", return_value=("Checklist.pdf", pdf)) as render:
			result = documents.generate_document(self.installation.name, kseb_checklist_print.CODE)
		render.assert_called_once()
		self.assertEqual(frappe.get_doc("File", {"file_url": result["file_url"]}).get_content(), pdf)
