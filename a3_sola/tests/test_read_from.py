# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Which document each field was read from is kept on the record (api/read_from): the proof
of a customer's name - "From Aadhaar card" under it on the form."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import read_from


class TestReadFrom(FrappeTestCase):
	def consumer(self, **values):
		doc = frappe.new_doc("Solar Consumer")
		doc.update(values)
		return doc

	def test_the_notes_are_kept(self):
		doc = self.consumer(consumer_name="C K Boban", bank_ifsc_code="SBIN0001234")
		read_from.set_posted(doc, {"a3s_read_from": json.dumps({"consumer_name": "Aadhaar card",
			"bank_ifsc_code": "Bank passbook"})})
		self.assertEqual(read_from.notes(doc), {"consumer_name": "Aadhaar card", "bank_ifsc_code": "Bank passbook"})

	def test_only_real_fields_holding_a_value_and_known_documents(self):
		doc = self.consumer(consumer_name="C K Boban")
		read_from.set_posted(doc, {"a3s_read_from": json.dumps({
			"consumer_name": "A letter I wrote",  # not a document the page reads
			"bank_account_no": "Bank passbook",  # blank on the record
			"no_such_field": "KSEB bill",
		})})
		self.assertIsNone(doc.a3s_read_from)

	def test_not_posted_changes_nothing_and_junk_is_ignored(self):
		doc = self.consumer(consumer_name="C K Boban", a3s_read_from='{"consumer_name": "Aadhaar card"}')
		read_from.set_posted(doc, {})
		read_from.set_posted(doc, {"a3s_read_from": "not json"})
		self.assertEqual(read_from.notes(doc), {"consumer_name": "Aadhaar card"})

	def test_cleared_by_the_form(self):
		doc = self.consumer(consumer_name="C K Boban", a3s_read_from='{"consumer_name": "Aadhaar card"}')
		read_from.set_posted(doc, {"a3s_read_from": ""})
		self.assertIsNone(doc.a3s_read_from)

	def test_every_form_that_reads_documents_keeps_them(self):
		for doctype in ("Solar Consumer", "Lead", "Installation Task", "Portal Application"):
			self.assertTrue(frappe.get_meta(doctype).get_field(read_from.FIELD), doctype)
