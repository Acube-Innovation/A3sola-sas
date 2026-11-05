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
