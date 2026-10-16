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


def attach(doctype, name, kind):
	return frappe.get_doc({
		"doctype": "File", "file_name": f"{kind.lower().replace(' ', '-')}.txt", "content": b"kyc", "is_private": 1,
		"attached_to_doctype": doctype, "attached_to_name": name, "a3s_document_type": kind,
	}).insert(ignore_permissions=True)


class TestPapersOnTheLeadOrTheCustomer(FrappeTestCase):
	"""A paper uploaded on the lead counts for its customer, and the other way round."""

	def test_a_paper_on_the_lead_counts_for_the_customer(self):
		consumer = make_consumer()
		self.assertTrue(consumer.lead)
		attach("Lead", consumer.lead, "PAN")
		for doctype, name in (("Solar Consumer", consumer.name), ("Lead", consumer.lead)):
			pan = next(i for i in kyc.summary(doctype, name)["items"] if i["label"] == "PAN")
			self.assertTrue(pan["uploaded"], doctype)
		kyc.refresh(consumer.name)
		self.assertNotIn("PAN", (frappe.db.get_value("Solar Consumer", consumer.name, "kyc_missing") or "").split(", "))

	def test_the_count_is_of_documents_not_fields(self):
		consumer = with_kyc(make_consumer(), FULL_SET)
		got = kyc.summary("Solar Consumer", consumer.name)
		self.assertEqual((got["uploaded"], got["pending"]), (got["total"], 0))
		consumer = with_kyc(make_consumer(), ("KSEB Bill",))
		got = kyc.summary("Solar Consumer", consumer.name)
		self.assertEqual(got["uploaded"], 1)
		self.assertEqual(got["pending"], got["total"] - 1)


class TestTheOrderTaskShowsTheCustomersKyc(FrappeTestCase):
	def test_customer_kyc_documents_follow_the_customer(self):
		from a3_sola.api.portal_tasks import KYC_DOCUMENTS, _panel

		inst = make_installation()
		if not any(d.document_name == KYC_DOCUMENTS for d in inst.documents):
			self.skipTest("no Customer KYC documents row in this site's order checklist")
		bill = attach("Solar Consumer", inst.solar_consumer, "KSEB Bill")
		row = next(d for d in _panel(frappe.get_doc("Solar Installation", inst.name), "ORD")["documents"]
			if d["name"].startswith(KYC_DOCUMENTS))
		self.assertIn(bill.file_url, [f["url"] for f in row["files"]])
		missing = [m["label"] for m in row["missing"]]
		self.assertNotIn("KSEB Bill", missing)
		self.assertIn("PAN", missing)
		self.assertEqual(row["missing"][0]["upload"]["kind"], "consumer")
