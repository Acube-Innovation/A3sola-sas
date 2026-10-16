# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 1 is the team's own form, its printed labels beside the customer's answers,
to view or download from the Form 1 Generation task."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import documents, form1_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestForm1Print(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def test_the_answers_are_the_customers(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		f = form1_print.context(inst)
		self.assertIn(inst.consumer_name, f.details)
		self.assertEqual(f.mounting, "Rooftop")
		self.assertEqual(f.date, frappe.utils.formatdate(frappe.utils.today(), "dd-MM-yyyy"))
		if frappe.utils.flt(inst.capacity_kw):
			self.assertEqual(f.capacity, "{0:g}KW".format(frappe.utils.flt(inst.capacity_kw)))

	def test_every_label_image_is_there(self):
		images = form1_print._images()
		self.assertEqual(set(images), set(form1_print.IMAGES))
		self.assertTrue(all(v.startswith("data:image/png;base64,") for v in images.values()))

	def test_the_task_offers_view_and_download(self):
		prints = portal_tasks._prints(frappe._dict(stage_code="FRM1"), self.installation.name)
		links = prints[form1_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Form 1", "Download Form 1"])
		self.assertTrue(links[1]["url"].endswith("&download=1"))

	def test_generating_form_1_attaches_this_form(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<p>Form 1</p>")
		with patch.object(form1_print, "render", return_value=("KSEBL Form 1.pdf", pdf)) as render:
			result = documents.generate_document(self.installation.name, form1_print.CODE)
		render.assert_called_once()
		content = frappe.get_doc("File", {"file_url": result["file_url"]}).get_content()
		self.assertEqual(content, pdf)
