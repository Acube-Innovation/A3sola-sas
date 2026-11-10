# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Jan Samarth asks for the pre-installation site photo and the Bank Quotation beside its approval
letter, each fetched where it already is: the photo from the customer, lead, survey or proposal,
the quotation printed from the job's own."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import loan_print, portal_tasks
from a3_sola.setup import seed_stages
from a3_sola.tests.solar_operations.fixtures import make_installation


def _row(name):
	return {"row": "r-" + name, "name": name, "mandatory": True, "kind": "Expected", "file_url": "", "prints": []}


class TestJanSamarthPapers(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def tearDown(self):
		frappe.db.rollback()

	def test_the_task_expects_the_letter_photo_and_quotation(self):
		expected = {name for name, _m, _t in seed_stages.checklists()["DAL"][1]}
		self.assertEqual(expected, {"Digital Approval Letter", "Pre-installation site photo", "Bank Quotation"})

	def test_the_customers_site_photo_is_fetched(self):
		url = frappe.get_doc({"doctype": "File", "file_name": "js-site.txt", "content": b"site photo", "is_private": 1,
			"attached_to_doctype": "Solar Consumer", "attached_to_name": self.installation.solar_consumer,
			"a3s_document_type": "Pre-Installation Photo"}).insert(ignore_permissions=True).file_url
		rows = portal_tasks.jan_samarth_rows(self.installation, [_row(portal_tasks.SITE_PHOTO)])
		self.assertEqual(rows[0]["kind"], "Uploaded")
		self.assertIn(url, [f["url"] for f in rows[0]["files"]])

	def test_the_customers_tax_papers_are_fetched(self):
		url = frappe.get_doc({"doctype": "File", "file_name": "js-land.txt", "content": b"land tax", "is_private": 1,
			"attached_to_doctype": "Solar Consumer", "attached_to_name": self.installation.solar_consumer,
			"a3s_document_type": "Land Tax Receipt"}).insert(ignore_permissions=True).file_url
		rows = {r["name"]: r for r in portal_tasks.customer_rows(self.installation, portal_tasks.JAN_SAMARTH_CUSTOMER)}
		self.assertEqual(list(rows), ["PAN", "Aadhaar", "Bank Proof", "KSEB Bill", "Income Tax Return",
			"Land Tax Receipt", "Building Tax Receipt"])
		self.assertEqual([f["url"] for f in rows["Land Tax Receipt"]["files"]], [url])
		self.assertEqual(rows["Land Tax Receipt"]["kind"], "Uploaded")
		# One the customer lacks is uploaded onto the customer.
		self.assertEqual(rows["Income Tax Return"]["missing"][0]["upload"],
			{"kind": "consumer", "consumer": self.installation.solar_consumer, "document_type": "Income Tax Return"})

	def test_the_panel_shows_the_customers_papers_first_and_the_letter_last(self):
		names = [d["name"] for d in portal_tasks._panel(self.installation, "DAL")["documents"]]
		self.assertEqual(names[:4], ["PAN", "Aadhaar", "Bank Proof", "KSEB Bill"])
		self.assertEqual(names[-1], "Digital Approval Letter")
		self.assertIn("Pre-Installation Site Photo", names)

	def test_form_1_shows_the_kseb_bill_and_aadhaar_first(self):
		url = frappe.get_doc({"doctype": "File", "file_name": "f1-bill.txt", "content": b"bill", "is_private": 1,
			"attached_to_doctype": "Solar Consumer", "attached_to_name": self.installation.solar_consumer,
			"a3s_document_type": "KSEB Bill"}).insert(ignore_permissions=True).file_url
		docs = portal_tasks._panel(self.installation, "FRM1")["documents"]
		self.assertEqual([d["name"] for d in docs[:2]], ["KSEB Bill", "Aadhaar"])
		self.assertIn(url, [f["url"] for f in docs[0]["files"]])
		self.assertIn("Annexure / Form 1", [d["name"] for d in docs[2:]])

	def test_with_no_photo_the_row_waits_for_its_upload(self):
		inst = frappe._dict(name=self.installation.name, solar_consumer=None, lead=None, site_survey=None,
			solar_proposal=None, quotation=None)
		rows = portal_tasks.jan_samarth_rows(inst, [_row(portal_tasks.SITE_PHOTO), _row(portal_tasks.BANK_QUOTATION)])
		self.assertEqual([r["kind"] for r in rows], ["Expected", "Expected"])
		self.assertNotIn("files", rows[0])

	def test_the_quotation_prints_on_the_task(self):
		prints = portal_tasks._prints(frappe._dict(stage_code="DAL"), self.installation.name)
		if not loan_print.has_quotation(self.installation):
			self.assertEqual(prints, {})
			return
		self.assertTrue(prints[loan_print.QUOTATION][0]["signable"])


class TestForm2Enclosures(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def tearDown(self):
		frappe.db.rollback()

	def names(self):
		return [d["name"] for d in portal_tasks._panel(frappe.get_doc("Solar Installation", self.installation.name),
			"FRM2")["documents"]]

	def test_form_2_lists_its_enclosures_in_order(self):
		self.assertEqual(self.names()[:7], ["KSEB Bill", "Annexure / Form 2", "Approved Single Line Diagram (SLD)",
			"Solar Panel Test Certificate", "Solar Panel Data Sheet", "Inverter Data Sheet", "Meter Test Certificate"])

	def test_the_sld_and_meter_certificate_are_fetched_from_their_tasks(self):
		from a3_sola.api import documents

		inst = frappe.get_doc("Solar Installation", self.installation.name)
		url = frappe.get_doc({"doctype": "File", "file_name": "f2-meter.txt", "content": b"meter", "is_private": 1,
			"attached_to_doctype": "Solar Installation", "attached_to_name": inst.name}).insert(ignore_permissions=True).file_url
		inst.flags.ignore_mandatory = True
		documents.register_document(inst, "MTR", "Solar Installation", inst.name, "Meter test certificate", url)
		docs = {d["name"]: d for d in portal_tasks._panel(frappe.get_doc("Solar Installation", inst.name), "FRM2")["documents"]}
		meter = docs["Meter Test Certificate"]
		self.assertEqual([f["url"] for f in meter["files"]], [url])
		self.assertEqual(meter["kind"], "Uploaded")
		self.assertEqual(self.names().count("Meter Test Certificate"), 1)
		sld = docs["Approved Single Line Diagram (SLD)"]
		if not sld["files"]:
			self.assertEqual(sld["missing"][0]["upload"]["document_name"], "Approved single line diagram")


class TestBankCompletionPrints(FrappeTestCase):
	"""Bank Completion Documents prints its letters live, with no pack to generate first."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def tearDown(self):
		frappe.db.rollback()

	def test_the_letters_print_live_on_the_task(self):
		from a3_sola.api import bank_completion_print, completion_print, vendor_agreement_print

		prints = portal_tasks._prints(frappe._dict(stage_code="BCOM"), self.installation.name)
		self.assertEqual(set(prints), set(bank_completion_print.CODES) | {vendor_agreement_print.CODE, completion_print.CODE})
		self.assertEqual(len(prints[bank_completion_print.REPORT]), 2)  # view and download

	def test_each_bank_letter_renders(self):
		from a3_sola.api import bank_completion_print

		inst = frappe.get_doc("Solar Installation", self.installation.name)
		for code in bank_completion_print.CODES:
			name, content = bank_completion_print.render(inst, code, signed=False)
			self.assertTrue(content.startswith(b"%PDF"))
			self.assertIn("(unsigned)", name)
		with self.assertRaises(frappe.ValidationError):
			bank_completion_print.render(inst, "KSEB-FORM-1")
