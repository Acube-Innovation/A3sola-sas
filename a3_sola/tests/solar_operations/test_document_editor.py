# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Editing a task's printed paper on the portal (api/document_editor): the editor gets the paper
as generated, the edit is printed in its place, reset brings the generated one back, nothing
unsafe is kept, the Bank Quotation and the project proposal are one edit, and the task's
panel offers Edit."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import document_editor, documents, form1_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation


def _text(pdf):
	return " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


class TestDocumentEditor(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_an_edit_prints_until_it_is_reset(self):
		name = self.installation.name
		loaded = document_editor.load(name, form1_print.CODE)
		self.assertFalse(loaded["edited"])
		state = document_editor.save(name, form1_print.CODE, loaded["html"] + "<p>Edited for the test</p>")
		self.assertTrue(state["edited"])
		self.assertIn("Edited for the test", _text(form1_print.render(name)[1]))
		self.assertTrue(document_editor.load(name, form1_print.CODE)["edited"])
		document_editor.reset(name, form1_print.CODE)
		self.assertNotIn("Edited for the test", _text(form1_print.render(name)[1]))

	def test_nothing_unsafe_is_kept(self):
		html = document_editor.clean('<p onclick="x()">a</p><script>alert(1)</script><a href="javascript:x()">l</a>'
			'<img src="data:image/png;base64,AAAA"><iframe src="https://x"></iframe><div contenteditable="true">d</div>')
		for bad in ("onclick", "<script", "javascript:", "<iframe", "contenteditable"):
			self.assertNotIn(bad, html)
		self.assertIn('src="data:image/png;base64,AAAA"', html)  # the form's images stay

	def test_the_bank_quotation_is_the_proposals_edit(self):
		self.assertEqual(documents.edit_key("BANK-QUOTATION"), "BANK-PROJECT-PROPOSAL")
		self.assertTrue(document_editor.editable("BANK-QUOTATION"))
		self.assertFalse(document_editor.editable("KYC"))

	def test_the_panel_offers_edit_on_printed_papers_only(self):
		panel = portal_tasks._panel(frappe.get_doc("Solar Installation", self.installation.name), "FRM1")
		edits = [d.get("edit") for d in panel["documents"] if d.get("prints")]
		self.assertTrue(edits and all(e and e["code"] == form1_print.CODE for e in edits))
		self.assertFalse([d for d in panel["documents"] if not d.get("prints") and d.get("edit")])
