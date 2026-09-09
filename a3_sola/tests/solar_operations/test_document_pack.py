# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Packs: generated item by item, merged into one file, complete when the recipient has them."""

import io

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_operations.doctype.document_pack import document_pack as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_agreement import execute as execute_agreement
from a3_sola.tests.solar_operations.test_tasks import task_row


def make_pack(installation, pack_type, **kwargs):
	values = {"doctype": "Document Pack", "solar_installation": installation.name, "pack_type": pack_type}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def page_count(file_url):
	from pypdf import PdfReader

	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	return len(PdfReader(io.BytesIO(content)).pages)


def encrypted_pdf():
	from pypdf import PdfWriter

	writer = PdfWriter()
	writer.add_blank_page(width=200, height=200)
	writer.encrypt("secret")
	out = io.BytesIO()
	writer.write(out)
	return out.getvalue()


class TestPackSetup(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_a_kseb_pack_starts_the_task_and_pulls_the_executed_agreement(self):
		agreement = execute_agreement(self.installation)
		pack = make_pack(self.installation, "KSEB Submission")
		self.assertEqual((pack.task_code, pack.solar_agreement), ("KFORMS", agreement.name))
		row, _doc = task_row(self.installation, "KFORMS")
		self.assertEqual((row.status, row.task_document), ("In Progress", pack.name))

	def test_a_bank_pack_is_refused_on_an_unfinanced_job(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_pack(self.installation, "Bank Completion Pack")
		self.assertIn("loan", str(ctx.exception).lower())

	def test_one_open_pack_per_type(self):
		make_pack(self.installation, "Customer Completion File")
		with self.assertRaises(frappe.ValidationError):
			make_pack(self.installation, "Customer Completion File")


class TestGeneration(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_items_generate_on_their_own_footing(self):
		"""No invoice, quotation or work order on this job: those items fail, the templates
		still render, and the failures are named."""
		pack = make_pack(self.installation, "Customer Completion File")
		result = ctl.generate_pack(pack.name)
		pack.reload()
		by_item = {r.template_code: r for r in pack.generated}
		for code in ("CUST-HANDOVER-PACK", "CUSTOMER-STATEMENT", "WARRANTY-CERTIFICATE", "CUSTOMER-CONTACTS", "KSEB-REFUND-REQUEST"):
			self.assertEqual(by_item[code].status, "Generated", code)
			self.assertTrue(by_item[code].file, code)
		self.assertEqual(by_item["@sales_invoice_print"].status, "Failed")
		self.assertIn("Tax invoice", pack.generation_notes)
		self.assertEqual(len(result["failed"]), 3)
		self.assertEqual(pack.status, "In Progress")
		# each generated file is on the job's register, sourced to this pack
		job = frappe.get_doc("Solar Installation", self.installation.name)
		sourced = [r for r in job.documents if r.source_document == pack.name and r.attachment]
		self.assertEqual(len(sourced), 5)

	def test_the_kseb_pack_prints_the_executed_agreement(self):
		execute_agreement(self.installation)
		pack = make_pack(self.installation, "KSEB Submission")
		ctl.generate_item(pack.name, "@agreement_print")
		pack.reload()
		row = next(r for r in pack.generated if r.template_code == "@agreement_print")
		self.assertTrue(row.file.endswith(".pdf"))
		self.assertGreaterEqual(page_count(row.file), 1)


class TestMerge(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_the_merge_has_every_page_and_names_what_it_skipped(self):
		pack = make_pack(self.installation, "Customer Completion File")
		ctl.generate_item(pack.name, "WARRANTY-CERTIFICATE")
		ctl.generate_item(pack.name, "CUSTOMER-CONTACTS")
		locked = frappe.get_doc(
			{"doctype": "File", "file_name": "bank-letter.pdf", "attached_to_doctype": "Document Pack",
			 "attached_to_name": pack.name, "is_private": 1, "content": encrypted_pdf()}
		).insert(ignore_permissions=True)
		ctl.attach_upload(pack.name, "Bank letter", locked.file_url)
		pack.reload()
		expected = sum(page_count(r.file) for r in pack.generated if r.file)
		result = ctl.merge_pdf(pack.name)
		pack.reload()
		self.assertEqual(page_count(pack.merged_pdf), expected)
		self.assertIn("password-protected", pack.merge_notes)
		self.assertEqual(result["documents"], 2)

	def test_an_empty_pack_cannot_be_merged(self):
		pack = make_pack(self.installation, "Customer Completion File")
		with self.assertRaises(frappe.ValidationError):
			ctl.merge_pdf(pack.name)


class TestCompletion(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_the_kseb_pack_completes_on_the_acknowledgement(self):
		execute_agreement(self.installation)
		pack = make_pack(self.installation, "KSEB Submission")
		with self.assertRaises(frappe.ValidationError):
			ctl.complete(pack.name)  # empty
		ctl.generate_item(pack.name, "KSEB-FORM-2")
		with self.assertRaises(frappe.ValidationError):
			ctl.complete(pack.name)  # not acknowledged
		ctl.mark_acknowledged(pack.name, acknowledgement_no="AE/ATH/2026/0042", ae_name="Smt. Latha")
		ctl.complete(pack.name)
		pack.reload()
		self.assertEqual((pack.docstatus, pack.status), (1, "Completed"))
		row, _doc = task_row(self.installation, "KFORMS")
		self.assertEqual((row.status, row.external_reference), ("Completed", "AE/ATH/2026/0042"))

	def test_the_customer_file_completes_on_handover(self):
		pack = make_pack(self.installation, "Customer Completion File")
		ctl.generate_item(pack.name, "CUSTOMER-CONTACTS")
		ctl.mark_sent(pack.name, reference="Rajagopalan", via="By Hand")
		ctl.complete(pack.name)
		pack.reload()
		self.assertEqual((pack.handed_over_to, pack.handover_mode), ("Rajagopalan", "By Hand"))
		row, _doc = task_row(self.installation, "CFILE")
		self.assertEqual(row.status, "Completed")

	def test_sending_records_the_email_and_the_delivery(self):
		consumer = frappe.get_doc("Solar Consumer", self.installation.solar_consumer)
		consumer.email_id = "customer@example.com"
		consumer.save(ignore_permissions=True)
		pack = make_pack(self.installation, "Customer Completion File")
		ctl.generate_item(pack.name, "CUSTOMER-CONTACTS")
		ctl.send(pack.name)
		pack.reload()
		self.assertEqual((pack.sent_to, pack.handover_mode), ("customer@example.com", "Email"))
		self.assertTrue(pack.merged_pdf and pack.handed_over_on)
		self.assertTrue(frappe.db.exists("Communication", {"reference_doctype": "Document Pack", "reference_name": pack.name}))
