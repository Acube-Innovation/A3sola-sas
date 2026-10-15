# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The loan application carries what the bank's documents print, and prints them.

The covering letter and vendor feasibility report are read at a bank counter against the
Word originals, so every value on them must be on the application - filled from the job
where it is known, and kept as typed where it is not.
"""

import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_operations.doctype.loan_application.loan_application import loan_defaults
from a3_sola.tests.solar_operations.fixtures import make_installation


def section_with_code(installation, code):
	"""The job's DISCOM section, given `code` - the section office's number."""
	frappe.db.set_value("DISCOM Section", installation.discom_section, "section_code", code)
	frappe.db.set_value("Solar Consumer", installation.solar_consumer, "discom_id", None)
	frappe.db.set_value("Solar Installation", installation.name, "discom_id", None)


def make_loan(installation, **kwargs):
	values = {
		"doctype": "Loan Application",
		"solar_installation": installation.name,
		"company": installation.company,
		"lender": "HDFC",
		"lender_branch": "Chalakudy",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


class TestLoanDocuments(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_the_discom_id_is_the_section_offices_code(self):
		self.assertTrue(self.installation.discom_section, "the fixture's job has no DISCOM section")
		section_with_code(self.installation, "5661")
		self.assertEqual(loan_defaults(self.installation.name)["discom_id"], "5661")

	def test_a_consumers_discom_id_follows_its_section(self):
		section_with_code(self.installation, "5661")
		consumer = frappe.get_doc("Solar Consumer", self.installation.solar_consumer)
		consumer.save(ignore_permissions=True)
		self.assertEqual(consumer.discom_id, "5661")

	def test_blanks_are_filled_from_the_job_and_typed_values_stand(self):
		loan = make_loan(self.installation, consumer_name="As On The Passbook", place="Aluva")
		consumer = frappe.db.get_value("Solar Consumer", self.installation.solar_consumer, "consumer_name")
		self.assertEqual((loan.consumer_name, loan.place), ("As On The Passbook", "Aluva"))
		self.assertNotEqual(loan.consumer_name, consumer)
		self.assertEqual(loan.discom_consumer_id, frappe.db.get_value("Solar Installation", self.installation.name, "consumer_number"))
		self.assertEqual(loan.project_cost_all_inclusive, 215000)

	def test_print_gives_both_documents_from_a_draft(self):
		from pypdf import PdfReader
		from io import BytesIO

		from a3_sola.api import loan_print

		loan = make_loan(self.installation, consumer_name="Printed Customer", loan_sanction_no="ANS-TEST-42")
		loan_print.pdf(loan.name)
		content = frappe.local.response.filecontent
		self.assertTrue(content.startswith(b"%PDF"))
		reader = PdfReader(BytesIO(content))
		text = " ".join(" ".join(page.extract_text() for page in reader.pages).split())
		self.assertEqual(len(reader.pages), 2)
		for expected in ("Printed Customer", "ANS-TEST-42", "Feasibility Report", "Submission of documents"):
			self.assertIn(expected, text)

	def test_the_patch_leaves_an_edited_template_alone(self):
		from a3_sola.patches.v1_2 import loan_documents_word_format as patch

		name = frappe.db.get_value("Solar Document Template", {"template_code": "BANK-COVERING-LOAN"}, "name")
		frappe.db.set_value("Solar Document Template", name, "body_template", "<p>Our own letter</p>")
		patch.execute()
		self.assertEqual(frappe.db.get_value("Solar Document Template", name, "body_template"), "<p>Our own letter</p>")
		self.assertNotEqual(hashlib.md5(b"<p>Our own letter</p>").hexdigest(), patch.SEEDED["BANK-COVERING-LOAN"])

	def test_print_without_sign_leaves_the_signature_and_seal_out(self):
		from a3_sola.api import documents

		def sign_hidden(signed):
			import frappe.utils.pdf as pdf_module

			captured = {}

			real = pdf_module.get_pdf
			pdf_module.get_pdf = lambda html, *a, **k: captured.setdefault("html", html) and b"%PDF"
			try:
				documents.letterhead_pdf(['<table class="a3s-sign"><tr><td>x</td></tr></table>'], self.installation.company, signed=signed)
			finally:
				pdf_module.get_pdf = real
			return ".a3s-sign { visibility: hidden; }" in captured["html"]

		self.assertFalse(sign_hidden(True))
		self.assertTrue(sign_hidden(False))

	def test_both_templates_mark_their_signature_and_seal(self):
		for code in ("BANK-COVERING-LOAN", "BANK-VENDOR-FEASIBILITY"):
			body = frappe.db.get_value("Solar Document Template", {"template_code": code}, "body_template")
			self.assertIn('class="a3s-sign"', body, code)

	def test_each_document_prints_on_one_page(self):
		from io import BytesIO

		from pypdf import PdfReader

		from a3_sola.api import loan_print

		loan = make_loan(self.installation, consumer_name="Printed Customer")
		for document, expected in (("letter", "Submission of documents"), ("feasibility", "Feasibility Report")):
			loan_print.pdf(loan.name, document=document, signed=0)
			reader = PdfReader(BytesIO(frappe.local.response.filecontent))
			self.assertEqual(len(reader.pages), 1, document)
			self.assertIn(expected, " ".join(reader.pages[0].extract_text().split()))
			self.assertIn("(unsigned)", frappe.local.response.filename)

	def test_the_bank_gets_a_rim_proposal_on_every_page(self):
		from io import BytesIO

		from pypdf import PdfReader

		from a3_sola.api import loan_print

		loan = make_loan(self.installation, consumer_name="Printed Customer")
		loan_print.pdf(loan.name, document="proposal")
		reader = PdfReader(BytesIO(frappe.local.response.filecontent))
		text = " ".join(" ".join(p.extract_text() for p in reader.pages).split())
		for expected in ("SOLAR PROJECT PROPOSAL", "Executive Summary", "Specifications", "Bank Account Details", "Scope of Work"):
			self.assertIn(expected, text)
		self.assertGreater(len(reader.pages), 1)

	def test_the_pack_holds_the_rim_proposal_and_opens_live(self):
		from a3_sola.api import portal_tasks

		loan = make_loan(self.installation)
		loan.generate_lender_pack()
		codes = {r.template_code: r.status for r in frappe.get_doc("Loan Application", loan.name).generated}
		self.assertEqual(codes.get("BANK-PROJECT-PROPOSAL"), "Generated")
		self.assertNotIn("PROPOSAL", codes, "the customer's own proposal is not the bank's")
		frappe.db.set_value("Solar Installation", self.installation.name, "loan_application", loan.name)
		row = next(r for r in frappe.get_doc("Solar Installation", self.installation.name).stages if r.stage_code == "LOAN")
		frappe.db.set_value(row.doctype, row.name, {"task_doctype": "Loan Application", "task_document": loan.name})
		panel = portal_tasks.task_documents(self.installation.name, "LOAN")
		printed = [d for d in panel["documents"] if d.get("prints")]
		self.assertEqual([d["name"] for d in printed], ["Covering letter", "Vendor feasibility report", "Quotation"])
		self.assertTrue(all("loan_print.pdf" in d["files"][0]["url"] for d in printed))

	def test_the_bank_gets_a_rim_quotation(self):
		from io import BytesIO

		from pypdf import PdfReader

		from a3_sola.api import loan_print

		loan = make_loan(self.installation)
		loan_print.pdf(loan.name, document="quotation")
		text = " ".join(" ".join(p.extract_text() for p in PdfReader(BytesIO(frappe.local.response.filecontent)).pages).split())
		self.assertIn("QUOTATION", text)
