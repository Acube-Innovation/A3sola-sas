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
