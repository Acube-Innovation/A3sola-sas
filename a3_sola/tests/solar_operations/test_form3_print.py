# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 3 is the team's own form, its printed labels beside the customer's answers, to
view or download from the Form 3 Submission task - whose Annexure / Form 3 row is Generated,
with no upload."""

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import form3_print, portal_tasks
from a3_sola.solar_operations.doctype.document_pack import document_pack as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_document_pack import make_pack
from a3_sola.www.a3solaportal import collections


class TestForm3Print(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def job(self):
		return frappe.get_doc("Solar Installation", self.installation.name)

	def test_the_answers_are_the_customers(self):
		inst = self.job()
		f = form3_print.context(inst)
		self.assertIn(inst.consumer_name, f.details)
		self.assertIn(inst.consumer_number, f.details)
		self.assertEqual((f.certificates, f.specifications), ("Yes", "Yes"))
		self.assertEqual(f.date, frappe.utils.formatdate(frappe.utils.today(), "dd-MM-yyyy"))

	def test_the_capacity_is_the_panels_kwp(self):
		inst = self.job()
		inst.set("panels", [])
		inst.append("panels", {"panel_capacity_wp": 550, "nos": 10})
		inst.append("panels", {"panel_capacity_wp": 600, "nos": 10, "is_option": 1})
		self.assertEqual(form3_print.context(inst).capacity, "5.5kWp")

	def test_the_registration_number_is_the_form_2_acknowledgement(self):
		inst = self.job()
		self.assertEqual(form3_print.context(inst).registration, "")
		make_pack(inst, "KSEB Form 2", ae_acknowledgement_no="SOL/REG/0042")
		self.assertEqual(form3_print.context(inst).registration, "SOL/REG/0042")

	def test_the_energisation_certificate_is_for_jobs_the_inspectorate_approves(self):
		inst = self.job()
		inst.set("stages", [r for r in inst.stages if r.stage_code != "CEIG"])
		self.assertEqual(form3_print.context(inst).inspectorate, "Not Applicable")
		inst.append("stages", {"stage_code": "CEIG", "status": "Skipped"})
		self.assertEqual(form3_print.context(inst).inspectorate, "Not Applicable")
		inst.stages[-1].status = "Completed"
		self.assertEqual(form3_print.context(inst).inspectorate, "Yes")

	def test_every_label_image_is_there(self):
		images = form3_print._images()
		self.assertEqual(set(images), set(form3_print.IMAGES) | set(form3_print.SHARED))
		self.assertTrue(all(v.startswith("data:image/png;base64,") for v in images.values()))

	def test_it_prints_on_one_page(self):
		name, pdf = form3_print.render(self.installation.name)
		reader = PdfReader(BytesIO(pdf))
		self.assertEqual(len(reader.pages), 1)
		self.assertIn(self.installation.consumer_number, reader.pages[0].extract_text())
		self.assertTrue(name.startswith("KSEBL Form 3 - "))

	def test_the_task_offers_view_and_download_and_takes_no_upload(self):
		links = portal_tasks._prints(frappe._dict(stage_code="KFORMS"), self.installation.name)[form3_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Form 3", "Download Form 3"])
		self.assertFalse(any(p.get("keep_file") for p in links))  # Generated: no upload
		self.assertTrue(links[1]["url"].endswith("&download=1"))
		page = collections.task_downloads(self.installation.name, "KFORMS")
		self.assertEqual([d["label"] for d in page][:2], ["View Form 3", "Download Form 3"])

	def test_the_ae_acknowledgement_is_not_a_document_of_the_task(self):
		from a3_sola.patches.v1_2 import drop_ae_acknowledged_form3

		inst = self.job()
		self.assertNotIn("AE acknowledged Form 3", [r.document_name for r in inst.documents])
		# A job from before: the patch drops the row still waiting, keeps one with its file.
		for attachment in (None, "/files/ae-ack.pdf"):
			inst.append("documents", {"stage_code": "KFORMS", "document_name": "AE acknowledged Form 3",
				"document_kind": "Expected", "attachment": attachment})
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		drop_ae_acknowledged_form3.execute()
		left = frappe.get_all("Installation Document", filters={"parent": inst.name, "document_name": "AE acknowledged Form 3"},
			pluck="attachment")
		self.assertEqual(left, ["/files/ae-ack.pdf"])

	def test_the_pack_generates_this_form(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Form 3</p>")
		pack = make_pack(self.installation, "KSEB Form 3")
		with patch.object(form3_print, "render", return_value=("KSEBL Form 3.pdf", pdf)) as render:
			ctl.generate_item(pack.name, form3_print.CODE)
		render.assert_called_once()
		row = next(r for r in frappe.get_doc("Document Pack", pack.name).generated if r.template_code == form3_print.CODE)
		self.assertEqual(frappe.get_doc("File", {"file_url": row.file}).get_content(), pdf)
