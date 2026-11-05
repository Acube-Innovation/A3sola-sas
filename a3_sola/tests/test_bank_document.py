# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A passbook's first page or a cancelled cheque is read into a customer's bank details
(api/bank_document), and an attached document is read again from the Attachments card
(api/portal_attachments.read_file)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import bank_document, portal_attachments

# Tesseract's text of a photographed cheque and passbook - their noise kept, the people made up.
CHEQUE = """
Hare Fa LA Canara Bank
Valid for three months only from the date of instrument
DB DBMMYY Y Y hind
TESTPURAM MAIN ROAD
TESTPURAM, KERALA - 680001
MULTI- CITY SB
Al ER Hl or Bearer
IFSC : CNRB0O01234
Rupees Bye
| ic.No.| 12345600098765
4£43¢95
Payable at par at all our branches in India
or
S019
ANNA VARGHESE
Please sign above
MGA329S" 680015903 oo. bB4i
"""

PASSBOOK = """
© SBI anda weBmanch: TESTNAGAR (CHALAKUDY) Code:
STATE BANKIOR MIPAMIPUZHA BUILDING i
Phone No.: 9100000001 suss. ff
Nana e eK Sabah fo iFsc: SBINO001234 MICR: 6
S/D/H/o > T K VARGHESE ene MOP: ST
CIF Number : 92500000001 eee A/c Ooe
Account Wo.-: 2 40000012345 ‘ Nom Rea
afe Type +: SAYINGS BANK ACCOUNT ~—— Custome
Name:
nl «<
Mr. T V Joseph
"""


class TestBankDocument(FrappeTestCase):
	def test_a_cheque(self):
		found = bank_document.parse(CHEQUE)
		self.assertEqual(found["ifsc"], "CNRB0001234")  # OCR's O for a zero put right
		self.assertEqual(found["account_no"], "12345600098765")  # "A/c.No" read as "ic.No"
		self.assertEqual(found["bank"], "Canara Bank")
		self.assertEqual(found["branch"], "TESTPURAM MAIN ROAD")
		self.assertEqual(found["name"], "ANNA VARGHESE")

	def test_a_passbook(self):
		found = bank_document.parse(PASSBOOK)
		self.assertEqual(found["ifsc"], "SBIN0001234")
		# Not the CIF number or the phone, though all are long numbers.
		self.assertEqual(found["account_no"], "40000012345")
		self.assertEqual(found["bank"], "State Bank of India")
		self.assertEqual(found["branch"], "TESTNAGAR (CHALAKUDY)")
		self.assertEqual(found["name"], "T V Joseph")

	def test_the_micr_band_is_not_the_account(self):
		found = bank_document.parse("IFSC: FDRL0001234\n\"123456\" 680049002: 000123\" 31\n")
		self.assertNotIn("account_no", found)

	def test_the_customers_fields(self):
		fields, warnings = bank_document.to_fields(bank_document.parse(CHEQUE))
		self.assertEqual(fields, {"bank_account_holder_name": "Anna Varghese", "bank_account_no": "12345600098765",
			"bank_name": "Canara Bank", "bank_branch": "Testpuram Main Road", "bank_ifsc_code": "CNRB0001234"})
		self.assertEqual(warnings, [])

	def test_what_was_not_read_is_a_warning(self):
		fields, warnings = bank_document.to_fields({"ifsc": "SBIN0001234", "bank": "State Bank of India"})
		self.assertNotIn("bank_account_no", fields)
		self.assertIn("account number", warnings[0])

	def test_bank_documents_on_a_customer_can_be_read_again(self):
		readers = {t for (dt, t) in portal_attachments.READERS if dt == "Solar Consumer"}
		self.assertTrue({"Bank Passbook", "Cancelled Cheque", "KSEB Bill", "Aadhaar Front", "Aadhaar Back"} <= readers)
		self.assertNotIn(("Lead", "Bank Passbook"), portal_attachments.READERS)

	def test_a_file_of_no_reader_is_not_read(self):
		consumer = frappe.get_all("Solar Consumer", limit=1, pluck="name")
		if not consumer:
			self.skipTest("No customer to attach to.")
		file = frappe.get_doc({"doctype": "File", "file_name": "note.txt", "content": b"hello", "is_private": 1,
			"attached_to_doctype": "Solar Consumer", "attached_to_name": consumer[0], "a3s_document_type": "Other"}).insert(
			ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "File", file.name, ignore_permissions=True, force=True)
		with self.assertRaises(frappe.ValidationError):
			portal_attachments.read_file("Solar Consumer", consumer[0], file.name)

	def test_a_customer_is_offered_its_five_document_types(self):
		self.assertEqual(portal_attachments.offered_types("Solar Consumer"),
			["Aadhaar Front", "Aadhaar Back", "KSEB Bill", "Bank Proof", "PAN"])
		# The KYC card's other papers are still accepted on the customer.
		self.assertIn("Pre-Installation Photo", portal_attachments.document_types("Solar Consumer"))
		# Other records keep their full list.
		self.assertIn("Other", portal_attachments.offered_types("Lead"))

	def test_a_bank_proof_is_read_and_counts_for_kyc(self):
		from a3_sola.api import kyc

		self.assertIn(("Solar Consumer", "Bank Proof"), portal_attachments.READERS)
		self.assertEqual(kyc.BANK_PROOF[0], "Bank Proof")
		self.assertIn("Bank Proof", frappe.get_meta("Customer KYC Document").get_options("kyc_type").split("\n"))
