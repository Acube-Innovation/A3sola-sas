# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What each of the customer's documents said, read by OCR, is kept and shown on the subsidy
eligibility check; where two documents differ, the check is submitted only once the details
are confirmed correct (api/document_evidence)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import document_evidence
from a3_sola.tests.fixtures import make_consumer


class TestDocumentEvidence(FrappeTestCase):
	def setUp(self):
		self.consumer = make_consumer(consumer_name="Manoj Prabhakaran")
		self.check = frappe._dict(doctype="Subsidy Eligibility Check", lead=None, solar_consumer=self.consumer.name)

	def document(self, doctype, name, document_type, fields):
		file = frappe.get_doc({"doctype": "File", "file_name": document_type + ".txt", "content": b"test", "is_private": 1,
			"attached_to_doctype": doctype, "attached_to_name": name, "a3s_document_type": document_type}).insert(
			ignore_permissions=True)
		document_evidence.store(file.name, fields)
		return file

	def test_each_detail_says_its_document(self):
		self.document("Solar Consumer", self.consumer.name, "Aadhaar Front", {"consumer_name": "Manoj Prabhakaran", "gender": "Male"})
		self.document("Solar Consumer", self.consumer.name, "KSEB Bill", {"consumer_name": "MANOJ PRABHAKARAN", "consumer_number": "1155904016772"})
		found = document_evidence.evidence(self.check)
		name = next(d for d in found["details"] if d["field"] == "consumer_name")
		self.assertEqual({v["document"] for v in name["values"]}, {"Aadhaar card", "KSEB bill"})
		# The same letters in another case are one spelling.
		self.assertFalse(name["conflict"])
		self.assertEqual(found["conflicts"], [])
		self.assertTrue(document_evidence.is_confirmed(self.check, found))

	def test_a_name_spelt_two_ways_is_a_conflict_to_confirm(self):
		self.document("Solar Consumer", self.consumer.name, "Aadhaar Front", {"consumer_name": "Manoj Prabhakaran"})
		self.document("Solar Consumer", self.consumer.name, "Cancelled Cheque", {"bank_account_holder_name": "Manoj P",
			"bank_ifsc_code": "CNRB0001234"})
		found = document_evidence.evidence(self.check)
		self.assertEqual([c["field"] for c in found["conflicts"]], ["consumer_name"])
		# The account holder is compared with the customer: the subsidy goes to the customer's account.
		holder = next(v for v in found["conflicts"][0]["values"] if v["document"] == "Cancelled cheque")
		self.assertEqual(holder["as"], "Account Holder Name")
		with self.assertRaises(frappe.ValidationError):
			document_evidence.assert_confirmed(self.check)
		self.check.documents_confirmed = found["signature"]
		document_evidence.assert_confirmed(self.check)

	def test_a_changed_document_asks_again(self):
		self.document("Solar Consumer", self.consumer.name, "Aadhaar Front", {"consumer_name": "Manoj Prabhakaran"})
		self.document("Solar Consumer", self.consumer.name, "KSEB Bill", {"consumer_name": "Manoj P"})
		self.check.documents_confirmed = document_evidence.evidence(self.check)["signature"]
		self.document("Solar Consumer", self.consumer.name, "Bank Passbook", {"bank_account_holder_name": "P Manoj"})
		self.assertFalse(document_evidence.is_confirmed(self.check))

	def test_the_leads_documents_count_too(self):
		lead = self.consumer.lead
		if not lead:
			self.skipTest("The customer has no lead.")
		self.document("Lead", lead, "KSEB Bill", {"lead_name": "Manoj P"})
		self.document("Solar Consumer", self.consumer.name, "Aadhaar Front", {"consumer_name": "Manoj Prabhakaran"})
		found = document_evidence.evidence(self.check)
		self.assertEqual([c["field"] for c in found["conflicts"]], ["consumer_name"])

	def test_a_document_not_read_is_listed(self):
		self.document("Solar Consumer", self.consumer.name, "Bank Passbook", None)
		docs = document_evidence.evidence(self.check)["documents"]
		self.assertEqual(len(docs), 1)
		self.assertEqual(docs[0]["fields"], {})

	def test_what_was_read_is_kept_on_the_file(self):
		file = self.document("Solar Consumer", self.consumer.name, "Bank Passbook", {"bank_ifsc_code": "SBIN0001234"})
		self.assertEqual(json.loads(frappe.db.get_value("File", file.name, "a3s_read_values")), {"bank_ifsc_code": "SBIN0001234"})


class TestLeadFollowsCustomer(FrappeTestCase):
	"""What a document gave the customer - or a correction since - shows on its lead too."""

	def test_the_customers_details_are_copied_to_its_lead(self):
		consumer = make_consumer(consumer_name="Typed Name")
		if not consumer.lead:
			self.skipTest("The customer has no lead.")
		consumer.reload()
		consumer.consumer_name = "C K Boban"
		consumer.consumer_number = "1155895007918"
		consumer.save(ignore_permissions=True)
		lead = frappe.db.get_value("Lead", consumer.lead, ["lead_name", "consumer_number"], as_dict=True)
		self.assertEqual(lead.lead_name, "C K Boban")
		self.assertEqual(lead.consumer_number, "1155895007918")


class TestDocumentCheckPaper(FrappeTestCase):
	"""The customer's documents as a PDF from the eligibility check, to view and send them."""

	def setUp(self):
		self.number = "555" + str(frappe.utils.random_string(10).encode().hex())[:10]
		self.consumer = make_consumer(consumer_name="Manoj Prabhakaran", consumer_number=self.number)
		self.check = frappe._dict(doctype="Subsidy Eligibility Check", name="TEST-ELG", lead=None,
			solar_consumer=self.consumer.name, consumer_name="Manoj Prabhakaran", company=self.consumer.company)
		TestDocumentEvidence.document(self, "Solar Consumer", self.consumer.name, "Aadhaar Front", {"consumer_name": "Manoj Prabhakaran"})
		TestDocumentEvidence.document(self, "Solar Consumer", self.consumer.name, "KSEB Bill",
			{"consumer_name": "Manoj P", "consumer_number": "1155895007918"})

	def test_the_paper_says_where_they_differ(self):
		from a3_sola.api import eligibility_print

		html = frappe.render_template("a3_sola/templates/print/eligibility_documents.html", eligibility_print.context(self.check))
		self.assertIn("The documents do not agree on: Customer Name", html)
		self.assertIn("may not be eligible for the subsidy", html)
		# The record's own consumer number is not the bill's: said too.
		self.assertIn("record differs from the documents on: Consumer Number", html)
		self.assertIn("On the customer&rsquo;s record: <strong>" + self.number + "</strong>", html)

	def test_it_can_be_sent_to_the_customer(self):
		from a3_sola.api import portal_share

		self.assertTrue(portal_share._sendable("Subsidy Eligibility Check"))
		self.assertIn("Subsidy Eligibility Check", portal_share.MESSAGES)


class TestProposedSystemAndLoad(FrappeTestCase):
	"""A rooftop system no larger than the connected load goes ahead; a larger one is said."""

	def setUp(self):
		self.consumer = make_consumer(consumer_name="Load Test")
		self.check = frappe._dict(doctype="Subsidy Eligibility Check", lead=None, solar_consumer=self.consumer.name,
			design_estimate=None, capacity_kw=0)

	def bill(self, watts):
		TestDocumentEvidence.document(self, "Solar Consumer", self.consumer.name, "KSEB Bill", {"connected_load_watts": watts})

	def test_a_system_over_the_connected_load_is_said(self):
		self.bill(1240)
		self.check.capacity_kw = 3
		load = document_evidence.load_check(self.check)
		self.assertFalse(load["ok"])
		self.assertEqual((load["capacity_w"], load["load_w"], load["over_w"], load["load_from"]), ("3000", "1240", "1760", "KSEB bill"))

	def test_a_system_within_the_load_is_fine(self):
		self.bill(5000)
		self.check.capacity_kw = 3
		self.assertTrue(document_evidence.load_check(self.check)["ok"])

	def test_nothing_is_said_without_a_capacity(self):
		self.bill(1240)
		if self.consumer.lead:
			frappe.db.set_value("Lead", self.consumer.lead, "approx_capacity_kw", 0)
		self.assertIsNone(document_evidence.load_check(self.check))


class TestAddressPriority(FrappeTestCase):
	def test_the_bills_permanent_address_is_not_compared_with_the_cards(self):
		consumer = make_consumer(consumer_name="Address Test")
		check = frappe._dict(doctype="Subsidy Eligibility Check", lead=None, solar_consumer=consumer.name)
		TestDocumentEvidence.document(self, "Solar Consumer", consumer.name, "KSEB Bill",
			{"site_address_line1": "DEVIPRIYA", "permanent_address_line1": "DEVIPRIYA"})
		TestDocumentEvidence.document(self, "Solar Consumer", consumer.name, "Aadhaar Back",
			{"permanent_address_line1": "Muttathukunnel House"})
		found = document_evidence.evidence(check)
		self.assertEqual(found["conflicts"], [])
		line1 = next(d for d in found["details"] if d["field"] == "permanent_address_line1")
		self.assertEqual([v["document"] for v in line1["values"]], ["Aadhaar card"])
