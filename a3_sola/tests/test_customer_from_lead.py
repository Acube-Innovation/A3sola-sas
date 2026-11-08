# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Create customer on a lead makes the customer at once, from the lead, and opens its edit
form - no create form in between (api/portal_chain.make_customer_from_lead)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_crud
from a3_sola.tests.fixtures import make_lead


class TestCustomerFromLead(FrappeTestCase):
	def test_made_at_once_and_opened_to_edit(self):
		lead = frappe.get_doc("Lead", make_lead(lead_name="Direct Customer"))
		# A lead without a consumer number yet: it comes later, from the KSEB bill.
		frappe.db.set_value("Lead", lead.name, "consumer_number", None)
		out = portal_crud.create_mapped(slug="consumers", source_dt="Lead", source=lead.name)
		self.assertTrue(out["route"].endswith("/consumers/" + out["name"] + "/edit"))
		consumer = frappe.get_doc("Solar Consumer", out["name"])
		self.assertEqual(consumer.consumer_name, "Direct Customer")
		self.assertEqual(consumer.lead, lead.name)
		self.assertTrue(consumer.discom)
		self.assertEqual(frappe.db.get_value("Lead", lead.name, "solar_consumer"), consumer.name)

	def test_a_second_click_opens_the_same_customer(self):
		lead = frappe.get_doc("Lead", make_lead(lead_name="Clicked Twice"))
		first = portal_crud.create_mapped(slug="consumers", source_dt="Lead", source=lead.name)
		second = portal_crud.create_mapped(slug="consumers", source_dt="Lead", source=lead.name)
		self.assertEqual(first["name"], second["name"])


class TestDocumentsOnANewCustomer(FrappeTestCase):
	"""A customer made from its lead has no consumer number yet: its documents go on all the same."""

	def setUp(self):
		lead = frappe.get_doc("Lead", make_lead(lead_name="Documents First"))
		frappe.db.set_value("Lead", lead.name, "consumer_number", None)
		lead.reload()
		self.consumer = portal_crud.create_mapped(slug="consumers", source_dt="Lead", source=lead.name)["name"]

	def file(self, kind, name="card.txt"):
		return frappe.get_doc({"doctype": "File", "file_name": name, "content": b"test", "is_private": 1,
			"attached_to_doctype": "Solar Consumer", "attached_to_name": self.consumer, "a3s_document_type": kind}).insert(
			ignore_permissions=True)

	def test_a_kyc_document_goes_on_without_the_consumer_number(self):
		from a3_sola.api import portal_attachments

		self.assertFalse(frappe.db.get_value("Solar Consumer", self.consumer, "consumer_number"))
		f = self.file("Aadhaar Front")
		portal_attachments._sync_kyc(self.consumer, f.file_url, "Aadhaar Front")
		kinds = frappe.get_all("Customer KYC Document", filters={"parent": self.consumer}, pluck="kyc_type")
		self.assertIn("Aadhaar Front", kinds)

	def test_a_pdf_with_both_sides_counts_for_both(self):
		from unittest.mock import patch

		from a3_sola.api import aadhaar_card, portal_attachments
		from a3_sola.tests.test_aadhaar_card import BACK, FRONT

		with patch.object(aadhaar_card.kseb_bill, "extract_text", return_value=(FRONT + "\n" + BACK, "pdf-text")):
			out = aadhaar_card.read_content(b"%PDF-1.4", "aadhaar.pdf", side="front")
		self.assertEqual(out["sides"], ["front", "back"])
		self.assertIn("consumer_name", out["fields"])
		self.assertIn("permanent_pincode", out["fields"])
		f = self.file("Aadhaar Front")
		portal_attachments._both_sides(self.consumer, f.file_url)
		kinds = frappe.get_all("Customer KYC Document", filters={"parent": self.consumer, "attachment": f.file_url}, pluck="kyc_type")
		self.assertEqual(sorted(kinds), ["Aadhaar Back", "Aadhaar Front"])


class TestEligibilityBeforeDesign(FrappeTestCase):
	"""On a customer's next steps the subsidy eligibility check comes before the design
	estimate; the design estimate is open from the start."""

	def estimate_step(self, consumer):
		from a3_sola.api import portal_chain

		steps = portal_chain.steps_for(frappe.get_doc("Solar Consumer", consumer))
		keys = [s["key"] for s in steps]
		self.assertLess(keys.index("eligibility"), keys.index("estimate"))
		return next(s for s in steps if s["key"] == "estimate")

	def test_the_design_estimate_is_open_without_a_check(self):
		from a3_sola.tests.fixtures import make_consumer

		self.assertFalse(self.estimate_step(make_consumer().name)["blocked"])


class TestLeadFilesOnTheCustomer(FrappeTestCase):
	"""Whatever is attached to the lead is attached to the customer made from it, and a file
	added to or removed from the lead later goes on or off the customer too."""

	def setUp(self):
		self.lead = make_lead(lead_name="Files Carried")
		frappe.db.set_value("Lead", self.lead, {"consumer_number": None, "gender": "Male"})

	def lead_file(self, kind=None, name="bill.txt", content=b"bill"):
		return frappe.get_doc({"doctype": "File", "file_name": name, "content": content, "is_private": 1,
			"attached_to_doctype": "Lead", "attached_to_name": self.lead, "a3s_document_type": kind}).insert(
			ignore_permissions=True)

	def customer_files(self, consumer):
		return {f.file_url: f.a3s_document_type for f in frappe.get_all("File", filters={
			"attached_to_doctype": "Solar Consumer", "attached_to_name": consumer}, fields=["file_url", "a3s_document_type"])}

	def make(self):
		return portal_crud.create_mapped(slug="consumers", source_dt="Lead", source=self.lead)["name"]

	def test_the_leads_files_and_gender_come_across(self):
		bill = self.lead_file("KSEB Bill")
		pan = self.lead_file("PAN", "pan.txt", b"pan")
		other = self.lead_file(None, "note.txt", b"note")
		consumer = self.make()
		files = self.customer_files(consumer)
		self.assertEqual(files.get(bill.file_url), "KSEB Bill")
		self.assertEqual(files.get(pan.file_url), "PAN")
		self.assertIn(other.file_url, files)
		kinds = frappe.get_all("Customer KYC Document", filters={"parent": consumer}, pluck="kyc_type")
		self.assertIn("PAN", kinds)
		self.assertEqual(frappe.db.get_value("Solar Consumer", consumer, "gender"), "Male")

	def test_a_file_added_to_the_lead_later_goes_on_the_customer(self):
		from a3_sola.api import portal_attachments

		consumer = self.make()
		f = self.lead_file("PAN", "pan.txt", b"later")
		portal_attachments.mirror_to_customer(self.lead, f.file_url, "PAN")
		self.assertEqual(self.customer_files(consumer).get(f.file_url), "PAN")
		self.assertIn("PAN", frappe.get_all("Customer KYC Document", filters={"parent": consumer}, pluck="kyc_type"))

		portal_attachments.unmirror_from_customer(self.lead, f.file_url)
		self.assertNotIn(f.file_url, self.customer_files(consumer))
		self.assertNotIn("PAN", frappe.get_all("Customer KYC Document", filters={"parent": consumer}, pluck="kyc_type"))

	def test_the_patch_fills_a_customer_made_before(self):
		from a3_sola.patches.v1_2 import lead_files_on_customer

		consumer = self.make()
		f = self.lead_file("KSEB Bill", "old.txt", b"before")  # as if it were on the lead, not carried
		frappe.db.set_value("Solar Consumer", consumer, "gender", None)
		lead_files_on_customer.execute()
		self.assertEqual(self.customer_files(consumer).get(f.file_url), "KSEB Bill")
		self.assertEqual(frappe.db.get_value("Solar Consumer", consumer, "gender"), "Male")
