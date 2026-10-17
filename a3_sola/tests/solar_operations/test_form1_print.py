# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 1 is the team's own form, its printed labels beside the customer's answers,
to view or download from the Form 1 Generation task - whose page says which of row 1's
details are still to be filled in, and where."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import documents, form1_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.www.a3solaportal import collections


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

	def test_the_capacity_is_the_inverters(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		inst.set("inverters", [])
		inst.append("inverters", {"inverter_capacity_kw": 1, "nos": 3})
		inst.append("inverters", {"inverter_capacity_kw": 5, "nos": 1, "is_option": 1})
		self.assertEqual(form1_print.context(inst).capacity, "3KW")

	def test_a_missing_row_1_detail_is_on_the_task_not_the_form(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		inst.set("inverters", [])
		frappe.db.set_value("Solar Consumer", inst.solar_consumer, "email_id", None)
		self.assertNotIn("missing", form1_print.context(inst))
		# Only row 1's details are listed: no inverters (row 3) is not.
		listed = form1_print.missing(inst)
		self.assertIn({"what": "Email address", "field": "Email"}, listed)
		self.assertLessEqual({m["what"] for m in listed}, {what for _key, what, _field in form1_print.ROW1})
		notice = collections.task_missing(inst.name, "FRM1")
		self.assertEqual(notice["items"], listed)
		self.assertTrue(notice["href"].endswith("/edit"))
		self.assertIsNone(collections.task_missing(inst.name, "F1PAY"))

	def test_once_filled_it_is_no_longer_listed(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		frappe.db.set_value("Solar Consumer", inst.solar_consumer, "email_id", "form1@example.com")
		self.assertIn("form1@example.com", form1_print.context(inst).details)
		self.assertNotIn("Email address", [m["what"] for m in form1_print.missing(inst)])

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
