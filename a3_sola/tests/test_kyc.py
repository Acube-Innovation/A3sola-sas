# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KYC: what the order needs from the consumer, where it lives, and where it ends up."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import kyc
from a3_sola.tests.fixtures import make_consumer
from a3_sola.tests.solar_operations.fixtures import make_installation

FULL_SET = ("KSEB Bill", "PAN", "Aadhaar Front", "Aadhaar Back", "Bank Passbook", "Pre-Installation Photo")


def with_kyc(consumer, kinds, **fields):
	consumer.set("kyc_documents", [{"kyc_type": k, "attachment": f"/files/{k.lower().replace(' ', '-')}.pdf"} for k in kinds])
	consumer.email_id = consumer.email_id or "consumer@example.com"
	consumer.landmark = "Opposite the temple"
	consumer.taluk = "Aluva"
	consumer.google_location_url = "https://maps.app.goo.gl/x"
	consumer.update(fields)
	consumer.save(ignore_permissions=True)
	return consumer


class TestWhatIsRequired(FrappeTestCase):
	def test_the_full_set_is_complete(self):
		consumer = with_kyc(make_consumer(), FULL_SET)
		self.assertEqual(consumer.kyc_status, "Complete")
		self.assertFalse(consumer.kyc_missing)

	def test_each_missing_item_is_named(self):
		consumer = with_kyc(make_consumer(), ("KSEB Bill", "PAN"))
		self.assertEqual(consumer.kyc_status, "Incomplete")
		for item in ("Aadhaar Front", "Aadhaar Back", "Pre-Installation Photo", "passbook"):
			self.assertIn(item, consumer.kyc_missing)

	def test_a_cancelled_cheque_on_the_bank_tab_is_bank_proof_enough(self):
		consumer = with_kyc(make_consumer(), [k for k in FULL_SET if k != "Bank Passbook"], cancelled_cheque="/files/cheque.pdf")
		self.assertEqual(consumer.kyc_status, "Complete")

	def test_a_large_loan_asks_for_income_or_land_proof(self):
		consumer = with_kyc(make_consumer(), FULL_SET)
		self.assertTrue(kyc.status(consumer, loan_amount=150000)["complete"])
		result = kyc.status(consumer, loan_amount=250000)
		self.assertFalse(result["complete"])
		self.assertTrue(any("Income tax" in str(m) for m in result["missing"]))
		consumer = with_kyc(consumer, FULL_SET + ("Land Tax Receipt",))
		self.assertTrue(kyc.status(consumer, loan_amount=250000)["complete"])

	def test_the_aadhaar_number_is_kept_as_its_last_four_digits(self):
		consumer = make_consumer()
		consumer.append("kyc_documents", {"kyc_type": "Aadhaar Front", "attachment": "/files/a.jpg", "document_no": "1234 5678 9012"})
		consumer.save(ignore_permissions=True)
		self.assertEqual(consumer.kyc_documents[0].document_no, "XXXX XXXX 9012")

	def test_the_google_location_is_composed_from_coordinates_when_blank(self):
		consumer = make_consumer()
		consumer.latitude, consumer.longitude, consumer.google_location_url = 10.09, 76.34, None
		consumer.save(ignore_permissions=True)
		self.assertIn("maps.google.com/?q=10.09", consumer.google_location_url)


class TestTheJobRegistersIt(FrappeTestCase):
	def test_kyc_files_reach_the_jobs_register_under_the_order_task(self):
		consumer = with_kyc(make_consumer(avg_consumption_units=750, sanctioned_load_kw=5), FULL_SET)
		installation = make_installation(consumer)
		kyc.register_for_installation(installation.name)
		doc = frappe.get_doc("Solar Installation", installation.name)
		rows = [r for r in doc.documents if r.source_doctype == "Solar Consumer"]
		self.assertEqual(len(rows), len(FULL_SET))
		self.assertTrue(all(r.stage_code == "ORD" for r in rows))
		self.assertTrue(any(r.document_name == "KYC - PAN" for r in rows))

	def test_a_file_added_later_reaches_the_open_job(self):
		consumer = with_kyc(make_consumer(avg_consumption_units=750, sanctioned_load_kw=5), ("KSEB Bill",))
		installation = make_installation(consumer)
		consumer.reload()
		consumer.append("kyc_documents", {"kyc_type": "PAN", "attachment": "/files/pan.pdf"})
		consumer.save(ignore_permissions=True)
		doc = frappe.get_doc("Solar Installation", installation.name)
		self.assertTrue(any(r.document_name == "KYC - PAN" for r in doc.documents))
