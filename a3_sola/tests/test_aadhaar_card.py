# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An Aadhaar card fills a customer's permanent address - and name, date of birth and gender -
and its number is never read. All details here are made up."""

import io
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import aadhaar_card, kseb_bill

BACK = """Unique Identification Authority of India
Address:
S/O Raju Varghese, Puthenveedu House,
Temple Road, Kakkanad, Ernakulam,
Kerala - 682030
1234 5678 9012
"""

LABELLED = """Address: C/O Joseph, Kunnel House, Near Church, VTC: Kalady, PO: Kalady, Sub District: Aluva,
District: Ernakulam, State: Kerala, PIN Code: 683574
"""

FRONT = """Government of India
Anna Varghese
DOB: 15/08/1990
FEMALE
2345 6789 0123
"""


class TestAadhaarCard(FrappeTestCase):
	def test_the_number_and_vid_are_taken_out_first(self):
		for number in ("1234 5678 9012", "123456789012", "9123 4567 8901 2345"):
			self.assertNotIn(number.replace(" ", ""), aadhaar_card.scrub(f"x {number} y").replace(" ", ""))
		# A PIN and a phone number are not Aadhaar numbers.
		self.assertIn("682030", aadhaar_card.scrub("Kerala - 682030"))
		self.assertIn("9847100302", aadhaar_card.scrub("Mobile 9847100302"))
		self.assertNotIn("123456789012", str(aadhaar_card.parse(BACK)).replace(" ", ""))

	def test_the_back_is_the_address_in_its_parts(self):
		a = aadhaar_card.parse(BACK)["address"]
		self.assertEqual((a["line1"], a["line2"], a["city"]), ("Puthenveedu House", "Temple Road", "Kakkanad"))
		self.assertEqual((a["district"], a["state"], a["pincode"]), ("Ernakulam", "Kerala", "682030"))

	def test_a_labelled_address_is_read_by_its_labels(self):
		a = aadhaar_card.parse(LABELLED)["address"]
		self.assertEqual((a["line1"], a["city"], a["district"], a["state"], a["pincode"]),
			("Kunnel House", "Kalady", "Ernakulam", "Kerala", "683574"))
		self.assertIn("Near Church", a["line2"])

	def test_the_front_is_the_holder(self):
		p = aadhaar_card.parse(FRONT)
		self.assertEqual((p["name"], p["dob"], p["gender"]), ("Anna Varghese", "15/08/1990", "Female"))

	def test_a_photographed_front_with_only_a_year_of_birth(self):
		# The Malayalam label before "/ Year of Birth" reads as noise on that line: the name is above it.
		p = aadhaar_card.parse("mM) O& eaureuMm\nK P Rajan\namm cudae/Year of Birth: 1967\nalam | Male\n")
		self.assertEqual((p["name"], p["year_of_birth"], p["gender"]), ("K P Rajan", "1967", "Male"))
		with patch.object(frappe.db, "exists", return_value=True):
			fields, warnings = aadhaar_card.to_fields(p)
		self.assertNotIn("date_of_birth", fields)
		self.assertIn("1967", warnings[0])

	def test_specks_at_the_cards_edge_are_not_address(self):
		self.assertEqual(aadhaar_card._parts("S/O: K P Raman, Kunnel House, Kalady Koratti, 4, 4 Kerala"),
			["Kunnel House", "Kalady Koratti", "Kerala"])

	def test_the_customers_fields(self):
		with patch.object(aadhaar_card, "find_state", return_value="Kerala"), \
				patch.object(aadhaar_card, "find_district", return_value="Ernakulam, Kerala"), \
				patch.object(frappe.db, "exists", return_value=True):
			fields, warnings = aadhaar_card.to_fields({**aadhaar_card.parse(FRONT), **aadhaar_card.parse(BACK)})
		self.assertEqual(warnings, [])
		# The card's address is where the person lives: the permanent address, not the site.
		self.assertEqual(fields["permanent_address_same"], "No")
		self.assertEqual((fields["permanent_district"], fields["permanent_pincode"]), ("Ernakulam, Kerala", "682030"))
		self.assertEqual((fields["consumer_name"], fields["date_of_birth"], fields["gender"]), ("Anna Varghese", "1990-08-15", "Female"))
		self.assertFalse(any(k.startswith("site_") for k in fields))

	def test_an_unknown_district_is_a_warning(self):
		with patch.object(aadhaar_card, "find_state", return_value="Kerala"), patch.object(aadhaar_card, "find_district", return_value=None):
			fields, warnings = aadhaar_card.to_fields({"address": {"district": "Nowhere", "state": "Kerala", "pincode": "682030"}})
		self.assertNotIn("permanent_district", fields)
		self.assertIn("Nowhere", warnings[0])

	def test_a_locked_pdf_needs_its_password(self):
		from frappe.utils.pdf import get_pdf
		from pypdf import PdfReader, PdfWriter

		writer = PdfWriter()
		for page in PdfReader(io.BytesIO(get_pdf("<p>Address: Puthenveedu House, Kakkanad, Ernakulam, Kerala - 682030</p>"))).pages:
			writer.add_page(page)
		writer.encrypt("ANNA1990")
		buf = io.BytesIO()
		writer.write(buf)
		locked = buf.getvalue()
		for password, title in ((None, kseb_bill.PASSWORD_NEEDED), ("WRONG", kseb_bill.WRONG_PASSWORD)):
			with self.assertRaises(frappe.ValidationError):
				kseb_bill.pdf_text(locked, password)
		self.assertIn("682030", kseb_bill.pdf_text(locked, "ANNA1990"))

	def test_a_card_kept_on_a_new_form_is_claimed(self):
		file = frappe._dict(name="F1", owner="Administrator", attached_to_doctype=None, a3s_document_type="Aadhaar Back",
			file_url="/private/files/back.jpg")
		with patch.object(frappe.db, "get_value", return_value=file), patch.object(frappe.db, "set_value") as set_value, \
				patch.object(kseb_bill, "kyc_rows") as rows:
			self.assertEqual(kseb_bill.claim("F1", "Solar Consumer", "CUST-1"), "/private/files/back.jpg")
		set_value.assert_called_once()
		rows.assert_called_once_with("Solar Consumer", "CUST-1", "/private/files/back.jpg", "Aadhaar Back")


class TestAadhaarSides(FrappeTestCase):
	""""Read Aadhaar front" and "Read Aadhaar back": each side gives only its own details, and
	the other side picked is said."""

	def read(self, text, side):
		with patch.object(aadhaar_card.kseb_bill, "extract_text", return_value=(text, "ocr")), \
				patch.object(aadhaar_card, "english_column", return_value=None), \
				patch.object(aadhaar_card, "_layout_text", return_value=""):
			return aadhaar_card.read_content(b"photo", "card.jpg", side=side)

	def test_the_front_gives_the_holder_only(self):
		out = self.read(FRONT, "front")
		self.assertEqual(out["side"], aadhaar_card.FRONT)
		self.assertIn("consumer_name", out["fields"])
		self.assertFalse([k for k in out["fields"] if k.startswith("permanent_")])

	def test_the_back_gives_the_address_only(self):
		out = self.read(BACK, "back")
		self.assertEqual(out["side"], aadhaar_card.BACK)
		self.assertIn("permanent_pincode", out["fields"])
		self.assertNotIn("consumer_name", out["fields"])

	def test_the_other_side_picked_is_said(self):
		with self.assertRaises(frappe.ValidationError):
			self.read(BACK, "front")
		with self.assertRaises(frappe.ValidationError):
			self.read(FRONT, "back")


# An e-Aadhaar letter as OCR reads it with its layout kept: the "To" block, the small print
# beside the card, both sides on one page. Made-up details.
LETTER = """Unique Identification Authority of India
Enrolment No.: 0000/00111/22222
To
Anna Varghese
C/O Joseph Varghese,
Kunne! House,
Kalady,
VTC: Kalady,
PO; Kalady,
District; Ernakulam,
State: Kerala,
PIN Code: 683574,
Mobile: 9000000001
Entities seeking Aadhaar are obligated to seek consent.
Date of Birth/DOB: 01/01/1990
Female/ FEMALE
Address:
C/O Joseph Varghese, Kunnel House, Kalady, PO: Kalady, DIST: Ernakulam,
Kerala - 683574"""


class TestAadhaarLetter(FrappeTestCase):
	def test_the_letter_gives_its_holder_and_address(self):
		got = aadhaar_card.parse(LETTER)
		# The "To" block's name - not the small print OCR read above the date of birth.
		self.assertEqual(got["name"], "Anna Varghese")
		self.assertEqual(got["dob"], "01/01/1990")
		self.assertEqual(got["address"]["pincode"], "683574")
		self.assertEqual(got["address"]["line1"], "Kunnel House")
		self.assertEqual(got["address"]["district"], "Ernakulam")

	def test_a_sentence_is_not_a_name(self):
		self.assertIsNone(aadhaar_card._as_name("Entities seeking Aadhaar are obligated to seek consent."))
		self.assertEqual(aadhaar_card._as_name("C K Boban"), "C K Boban")

	def test_a_photo_with_both_sides_counts_for_both(self):
		with patch.object(aadhaar_card.kseb_bill, "extract_text", return_value=(LETTER, "ocr")), \
				patch.object(aadhaar_card, "english_column", return_value=None), \
				patch.object(aadhaar_card, "_layout_text", return_value=""):
			out = aadhaar_card.read_content(b"photo", "letter.jpg", side="front")
		self.assertEqual(out["sides"], ["front", "back"])
		self.assertIn("permanent_pincode", out["fields"])
