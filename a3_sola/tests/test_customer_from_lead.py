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
