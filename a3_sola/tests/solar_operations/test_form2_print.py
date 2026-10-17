# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 2 is the team's own form, its printed labels beside the customer's answers, to
view or download from the Form 2 Submission task - whose Annexure / Form 2 row is Generated,
with no upload."""

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import form2_print, portal_tasks
from a3_sola.solar_operations.doctype.document_pack import document_pack as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_document_pack import make_pack
from a3_sola.www.a3solaportal import collections


class TestForm2Print(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def job(self):
		return frappe.get_doc("Solar Installation", self.installation.name)

	def test_the_answers_are_the_customers(self):
		inst = self.job()
		f = form2_print.context(inst)
		self.assertIn(inst.consumer_name, f.details)
		self.assertIn(inst.consumer_number, f.details)
		self.assertEqual((f.specifications, f.drawings), ("Yes", "Yes"))
		self.assertEqual(f.date, frappe.utils.formatdate(frappe.utils.today(), "dd-MM-yyyy"))

	def test_the_load_is_in_kw(self):
		inst = self.job()
		frappe.db.set_value("Solar Consumer", inst.solar_consumer, {"connected_load_watts": 3000, "sanctioned_load_kw": 5})
		self.assertEqual(form2_print.context(inst).load, "3kW")
		frappe.db.set_value("Solar Consumer", inst.solar_consumer, "connected_load_watts", 0)
		inst.connected_load_watts = 0
		self.assertEqual(form2_print.context(inst).load, "5kW")

	def test_the_capacity_is_the_panels_kwp(self):
		inst = self.job()
		inst.set("panels", [])
		inst.append("panels", {"panel_capacity_wp": 550, "nos": 10})
		inst.append("panels", {"panel_capacity_wp": 600, "nos": 10, "is_option": 1})
		self.assertEqual(form2_print.context(inst).capacity, "5.5kWp")

	def test_the_net_meter_is_the_customers_or_ksebls(self):
		inst = self.job()
		inst.net_meter_mode = "Purchased by Customer"
		self.assertEqual(form2_print.context(inst).meters, ["Solar Meter – Yes", "Net Meter – Yes"])
		inst.net_meter_mode = "Availed from DISCOM on Rental"
		self.assertEqual(form2_print.context(inst).meters,
			["Solar Meter – Yes", "Net Meter – From KSEBL", "(Request Attached)"])

	def test_row_7_is_when_the_installation_is_done(self):
		inst = self.job()
		row = next(r for r in inst.stages if r.stage_code == "IWOI")
		row.planned_date, row.actual_completion_date = "2026-05-15", None
		self.assertEqual(form2_print.context(inst).complete_by, "15.05.2026")
		row.actual_completion_date = "2026-05-12"
		self.assertEqual(form2_print.context(inst).complete_by, "12.05.2026")

	def test_every_label_image_is_there(self):
		images = form2_print._images()
		self.assertEqual(set(images), set(form2_print.IMAGES) | set(form2_print.SHARED))
		self.assertTrue(all(v.startswith("data:image/png;base64,") for v in images.values()))

	def test_it_prints_on_one_page(self):
		name, pdf = form2_print.render(self.installation.name)
		reader = PdfReader(BytesIO(pdf))
		self.assertEqual(len(reader.pages), 1)
		self.assertIn(self.installation.consumer_number, reader.pages[0].extract_text())
		self.assertTrue(name.startswith("KSEBL Form 2 - "))

	def test_the_task_offers_view_and_download_and_takes_no_upload(self):
		links = portal_tasks._prints(frappe._dict(stage_code="FRM2"), self.installation.name)[form2_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Form 2", "Download Form 2"])
		self.assertFalse(any(p.get("keep_file") for p in links))  # Generated: no upload
		self.assertTrue(links[1]["url"].endswith("&download=1"))
		page = collections.task_downloads(self.installation.name, "FRM2")
		self.assertEqual([d["label"] for d in page], ["View Form 2", "Download Form 2"])

	def test_the_pack_generates_this_form(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Form 2</p>")
		pack = make_pack(self.installation, "KSEB Form 2")
		with patch.object(form2_print, "render", return_value=("KSEBL Form 2.pdf", pdf)) as render:
			ctl.generate_item(pack.name, form2_print.CODE)
		render.assert_called_once()
		row = next(r for r in frappe.get_doc("Document Pack", pack.name).generated if r.template_code == form2_print.CODE)
		self.assertEqual(frappe.get_doc("File", {"file_url": row.file}).get_content(), pdf)
