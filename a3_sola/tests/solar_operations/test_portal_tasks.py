# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task card's Documents panel: the job's register rows for the task, with files to
open, uploads for the missing ones, and the loan's prints."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from werkzeug.datastructures import FileStorage, MultiDict

from a3_sola.api import portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation


def posted(name="sanction.txt", content=b"Sanction letter"):
	return SimpleNamespace(files=MultiDict({"file": FileStorage(stream=BytesIO(content), filename=name)}))


class TestTaskDocuments(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def expected_row(self, code):
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		return next((r for r in doc.documents if r.stage_code == code and not r.attachment), None)

	def test_the_panel_lists_the_tasks_register_rows(self):
		row = self.expected_row("BCOM")
		self.assertTrue(row, "the job has no expected BCOM document")
		panel = portal_tasks.task_documents(self.installation.name, "BCOM")
		self.assertEqual(panel["task"]["code"], "BCOM")
		names = [d["name"] for d in panel["documents"]]
		self.assertIn(row.document_name, names)


	def test_an_upload_fills_the_expected_row(self):
		row = self.expected_row("BCOM")
		with patch.object(frappe, "request", posted()):
			panel = portal_tasks.upload(self.installation.name, "BCOM", row=row.name)
		filled = next(d for d in panel["documents"] if d["row"] == row.name)
		self.assertEqual(filled["kind"], "Uploaded")
		self.assertTrue(filled["file_url"].startswith("/private/files/"))

	def test_another_document_needs_a_name(self):
		with patch.object(frappe, "request", posted()):
			with self.assertRaises(frappe.ValidationError):
				portal_tasks.upload(self.installation.name, "BCOM")
			panel = portal_tasks.upload(self.installation.name, "BCOM", document_name="Bank query reply")
		self.assertIn("Bank query reply", [d["name"] for d in panel["documents"]])


class TestStampPaperTask(FrappeTestCase):
	"""Buying the stamp paper is one tick box, and its data sheet downloads from the job."""

	def setUp(self):
		self.installation = make_installation()

	def create(self, **values):
		from a3_sola.api import portal_crud

		made = portal_crud.create_record(
			slug="agreements", source_dt="Solar Installation", source=self.installation.name, source_task="STMP", **values
		)
		return frappe.get_doc("Solar Agreement", made["name"])

	def stmp_row(self):
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		return next(r for r in doc.stages if r.stage_code == "STMP")

	def test_the_form_asks_whether_it_was_bought_and_who_is_paid_back(self):
		from a3_sola.www.a3solaportal.collections import task_form_groups

		values = {"solar_installation": self.installation.name, "task_code": "STMP"}
		_doc, groups = task_form_groups("agreements", values)
		specs = [f for g in groups for s in g["sections"] for f in s["fields"]]
		self.assertEqual(
			[(f["fieldname"], f["type"]) for f in specs],
			[("stamp_paper_status", "Check"), ("claim_reimbursement", "Check"),
			 ("stamp_paper_value", "Currency"), ("stamp_paper_remarks", "Small Text")],
		)
		claim = next(f for f in specs if f["fieldname"] == "claim_reimbursement")
		self.assertEqual(claim["show_when"], "stamp_paper_status")

	def test_ticked_is_purchased_and_completes_the_task(self):
		agreement = self.create(stamp_paper_status="1")
		self.assertEqual(agreement.stamp_paper_status, "Purchased")
		self.assertEqual(self.stmp_row().status, "Completed")

	def test_unticked_is_not_purchased_yet(self):
		agreement = self.create(stamp_paper_status="0")
		self.assertEqual(agreement.stamp_paper_status, "Not Purchased")
		self.assertNotEqual(self.stmp_row().status, "Completed")

	def test_the_data_sheet_downloads_from_the_job(self):
		from pypdf import PdfReader

		from a3_sola.api import stamp_print

		stamp_print.pdf(self.installation.name)
		text = " ".join(PdfReader(BytesIO(frappe.local.response.filecontent)).pages[0].extract_text().split())
		consumer = frappe.db.get_value("Solar Consumer", self.installation.solar_consumer, "consumer_name")
		for expected in (consumer.upper(), "The Assistant Engineer", "Solar Agreement", "Rs."):
			self.assertIn(expected, text)
		panel = portal_tasks.task_documents(self.installation.name, "STMP")
		sheet = next(d for d in panel["documents"] if d["name"] == "Stamp paper data sheet")
		self.assertTrue(sheet["prints"] and "stamp_print.pdf" in sheet["prints"][0]["url"])


class TestLoanPack(FrappeTestCase):
	"""Loan Documents lists what the bank receives: our RIM prints, the Jan Samarth approval
	and the consumer's own papers, each with an upload while missing."""

	def setUp(self):
		self.installation = make_installation(is_financed=1)

	def test_the_pack_is_the_banks_list_in_order(self):
		panel = portal_tasks.task_documents(self.installation.name, "LOAN")
		self.assertEqual([d["name"] for d in panel["documents"]], [
			"Covering letter", "Vendor feasibility report", "Quotation", "Jan Samarth approval letter",
			"PM Surya Ghar registration", "KYC",
			"KSEB bill", "Land tax receipt", "Building tax receipt", "Income tax return (ITR)",
		])
		kyc = next(d for d in panel["documents"] if d["name"] == "KYC")
		self.assertEqual([m["label"] for m in kyc["missing"]], ["Aadhaar Front", "Aadhaar Back", "PAN"])
		self.assertTrue(panel["fixed"])

	def test_a_consumer_paper_uploaded_shows_in_the_pack(self):
		from a3_sola.api import portal_attachments

		consumer = self.installation.solar_consumer
		with patch.object(frappe, "request", posted("bill.txt", b"KSEB bill")):
			portal_attachments.upload("Solar Consumer", consumer, document_type="KSEB Bill")
		panel = portal_tasks.task_documents(self.installation.name, "LOAN")
		bill = next(d for d in panel["documents"] if d["name"] == "KSEB bill")
		self.assertEqual((len(bill["files"]), bill["missing"]), (1, []))

	def test_a_paper_uploaded_on_the_pm_surya_ghar_task_shows_in_the_pack(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		npa = next((r for r in inst.stages if r.stage_code == portal_tasks.SURYA_GHAR_TASK), None)
		if not npa or npa.status == "Skipped":
			self.skipTest("the PM Surya Ghar task does not apply to this job")
		with patch.object(frappe, "request", posted("ack.txt", b"Portal acknowledgement")):
			portal_tasks.upload(self.installation.name, "NPA", document_name="Portal acknowledgement")
		panel = portal_tasks.task_documents(self.installation.name, "LOAN")
		row = next(d for d in panel["documents"] if d["name"] == "PM Surya Ghar registration")
		self.assertIn("Portal acknowledgement", [f["label"] for f in row["files"]])
		self.assertNotIn("Portal acknowledgement", [m["label"] for m in row["missing"]])

	def test_the_approval_letter_task_needs_its_letter(self):
		row = next(r for r in frappe.get_doc("Solar Installation", self.installation.name).stages if r.stage_code == "DAL")
		self.assertEqual(row.status, "Pending")
		task = frappe.get_doc({"doctype": "Installation Task", "solar_installation": self.installation.name, "task_code": "DAL"})
		task.flags.ignore_permissions = True
		task.insert(ignore_permissions=True)
		from a3_sola.solar_operations.doctype.installation_task.installation_task import complete

		with self.assertRaises(frappe.ValidationError):
			complete(task.name)
		with patch.object(frappe, "request", posted("approval.txt", b"approved")):
			portal_tasks.upload(self.installation.name, "DAL", document_name="Jan Samarth approval letter")
		complete(task.name)
		panel = portal_tasks.task_documents(self.installation.name, "LOAN")
		letter = next(d for d in panel["documents"] if d["name"] == "Jan Samarth approval letter")
		self.assertEqual(len(letter["files"]), 1)

	def test_a_self_funded_job_skips_the_approval(self):
		job = make_installation(is_financed=0)
		row = next(r for r in frappe.get_doc("Solar Installation", job.name).stages if r.stage_code == "DAL")
		self.assertEqual(row.status, "Skipped")

	def test_jan_samarth_is_in_the_pm_surya_ghar_column_of_a_loan_job_only(self):
		from a3_sola.www.a3solaportal.project_overview import _task_columns

		def column_of(job):
			columns = _task_columns(frappe.get_doc("Solar Installation", job.name))
			return next((c["label"] for c in columns for t in c["tasks"] if t.get("code") == "DAL"), None)

		self.assertEqual(column_of(make_installation(is_financed=1)), "PM Surya Ghar")
		self.assertIsNone(column_of(make_installation(is_financed=0)))
