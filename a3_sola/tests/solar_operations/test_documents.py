# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The document engine.

The whole point is that one context builder feeds every template, so the consumer number on
the bank letter and the consumer number on the DISCOM annexure cannot differ.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import documents
from a3_sola.tests.fixtures import default_company
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestDocumentContext(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_context_carries_the_shared_facts(self):
		ctx = documents.get_document_context(self.installation)
		self.assertEqual(ctx.installation.name, self.installation.name)
		self.assertEqual(ctx.consumer.consumer_number, self.installation.consumer_number)
		self.assertTrue(ctx.company)
		self.assertTrue(ctx.settings)

	def test_every_template_sees_the_same_consumer_number(self):
		"""The failure this engine exists to prevent."""
		ctx = documents.get_document_context(self.installation)
		self.assertEqual(ctx.consumer.consumer_number, ctx.installation.consumer_number)

	def test_template_set_resolves(self):
		self.assertTrue(documents.resolve_template_set(self.installation))


class TestDocumentGeneration(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_generate_one_document(self):
		result = documents.generate_document(self.installation.name, "MNRE-CONSUMER-VENDOR-AGREEMENT")
		self.assertTrue(result["file_url"])
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(len(doc.generated_documents), 1)
		self.assertEqual(doc.generated_documents[0].is_stale, 0)

	def test_regenerating_replaces_rather_than_duplicates(self):
		documents.generate_document(self.installation.name, "MNRE-CONSUMER-VENDOR-AGREEMENT")
		documents.generate_document(self.installation.name, "MNRE-CONSUMER-VENDOR-AGREEMENT")
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(len(doc.generated_documents), 1)

	def test_generated_document_files_into_the_checklist(self):
		documents.generate_document(self.installation.name, "MNRE-CONSUMER-VENDOR-AGREEMENT")
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		row = next(r for r in doc.documents if r.stage_code == "ORD" and r.is_mandatory)
		self.assertTrue(row.attachment)

	def test_pack_generates_many_and_reports_per_document(self):
		results = documents.generate_document_pack(self.installation.name)
		self.assertGreater(len(results), 5)
		self.assertTrue(all(r["status"] in ("generated", "failed") for r in results))
		self.assertTrue(any(r["status"] == "generated" for r in results))

	def test_unknown_template_raises(self):
		with self.assertRaises(frappe.ValidationError):
			documents.generate_document(self.installation.name, "NO-SUCH-TEMPLATE")

	def test_editing_the_consumer_number_marks_documents_stale(self):
		"""An issued letter carrying the old number has left the building."""
		documents.generate_document(self.installation.name, "MNRE-CONSUMER-VENDOR-AGREEMENT")
		consumer = frappe.get_doc("Solar Consumer", self.installation.solar_consumer)
		consumer.consumer_number = "1156540099999"
		consumer.save(ignore_permissions=True)

		doc = frappe.get_doc("Solar Installation", self.installation.name)
		self.assertEqual(doc.generated_documents[0].is_stale, 1)
		self.assertGreaterEqual(doc.stale_document_count, 1)


class TestSeededTemplates(FrappeTestCase):
	EXPECTED = [
		"MNRE-CONSUMER-VENDOR-AGREEMENT",
		"NP-APPLICATION",
		"NP-COMPLETION-REPORT",
		"BANK-COVERING-LOAN",
		"BANK-VENDOR-FEASIBILITY",
		"BANK-EHS-CHECKLIST",
		"BANK-COMPLETION-REPORT",
		"BANK-COVERING-COMPLETION",
		"KSEB-COVERING-COMPLETION",
		"KSEB-NETMETER-REQUEST",
		"KSEB-REFUND-REQUEST",
		"KSEB-FORM-1",
		"KSEB-FORM-2",
		"KSEB-FORM-3",
		"KSEB-TESTING-CHECKLIST",
		"KSEB-NETMETER-AGREEMENT",
		"CUST-COMMISSIONING-CERTIFICATE",
		"CUST-HANDOVER-PACK",
	]

	def test_every_client_document_has_a_template(self):
		company = default_company()
		for code in self.EXPECTED:
			self.assertTrue(
				frappe.db.exists("Solar Document Template", {"template_code": code, "company": company}),
				f"missing template {code}",
			)

	def test_every_template_records_its_source(self):
		"""So a reviewer can diff each against the client's own form."""
		company = default_company()
		for code in self.EXPECTED:
			notes = frappe.db.get_value(
				"Solar Document Template", {"template_code": code, "company": company}, "notes"
			)
			self.assertTrue(notes, f"{code} has no source note")

	def test_stamp_paper_flagged_on_the_agreement(self):
		company = default_company()
		row = frappe.db.get_value(
			"Solar Document Template",
			{"template_code": "KSEB-NETMETER-AGREEMENT", "company": company},
			["requires_stamp_paper", "signatory"],
			as_dict=True,
		)
		self.assertEqual(row.requires_stamp_paper, 1)
		self.assertEqual(row.signatory, "Consumer and Two Witnesses")

	def test_covering_letter_lists_its_enclosures(self):
		"""The client's letter names eight attachments; the template must carry them."""
		company = default_company()
		enclosures = frappe.db.get_value(
			"Solar Document Template",
			{"template_code": "KSEB-COVERING-COMPLETION", "company": company},
			"attachment_checklist",
		)
		lines = [line for line in (enclosures or "").split("\n") if line.strip()]
		self.assertGreaterEqual(len(lines), 8)
		self.assertTrue(any("stamp paper" in line.lower() for line in lines))
