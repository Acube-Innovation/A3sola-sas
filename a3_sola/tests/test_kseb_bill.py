# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A KSEB bill is read by its labels - from a PDF's text, or a photo through OCR - into the
lead's or customer's fields, its DISCOM, section and tariff found among their records."""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import kseb_bill

# The layout of a KSEB e-bill's text (Demand cum Disconnection Notice), with made-up details.
EBILL = """
                                          KERALA STATE ELECTRICITY BOARD LIMITED
                                                       DEMAND CUM DISCONNECTION NOTICE
Section          [4321]-Electrical Section Testpuram                                   Phone#            0484-0000000              Customer Care              1912
Consumer#        1100000000001                                    Reg. Mob# 900xxxx000                    Regular CC Bill(PostPaid)      KSEBL GSTIN: 32AAECK2277NBZ1
Name & Mailing Address                                            For redressing complaints/grievance approach the concerned CGRF

ANNA VARGHESE                                                     South: Chairperson,CGRF(South),KSEBL,Vydyuthi Bhavanam, Kottarakkara-691506, Ph:0474-2451300

ANNA VARGHESE, HOUSE NO.1, PUTHENVEEDU LANE N                     Central: Chairperson,CGRF(Central),KSEBL,220KV SubStation,Kalamassery-683503,Ph:0484-2556500

EAR TEMPLE, KAKKANAD 682030                                       North: Chairperson,CGRF(North),KSEBL,Vydyuthi Bhavanam,Gandhi Rd.,Kozhikode-673011,Ph:0495-2367820

Bill#                       4321260708082                             Bill Area                 A01/18            DTR                       TESTDTR
Billing Period              7/2026[Bi-Monthly]                        Tariff/Phase              LT-1/Single       Pole#                     MS-1/1/1
Bill Date                   20-07-2026                                Due Date                  30-07-2026        DC Date                   14-08-2026
Contract Demand             (Nil) VA [75% : 0KV, 130% : 0KV]          Connected Load            4200 Watts        Security Deposit          Rs.3000.00
           KWH                 Normal             Import                   5344.00                  5627.00                  1                              283
           KWH                 Off Peak           Import                   7452.00                  7794.00                  1                              142
           KWH                  Peak              Import                   5147.00                  5260.00                  1                              113
                   e)    Total Amt.(Bill#4321260708082)     (a+b+c+d)                 4210.00
"""

# A phone photo read by OCR: labels spaced and punctuated loosely, one column.
SPOT_BILL = """KERALA STATE ELECTRICITY BOARD
Section : [4321] - Testpuram
Consumer No : 1100000000002
Name & Address
MARY JOSEPH
KOLLAM 691001
Bill No: 123
Tariff : LT 1 A Phase : 1
Connected Load : 3.5 kW
Billing Period: Monthly
Units Consumed : 180
Net Amount : 1,250.00
Bill Date : 05/07/2026
"""


class TestKSEBBill(FrappeTestCase):
	def test_an_ebill_is_read_by_its_labels(self):
		p = kseb_bill.parse(EBILL)
		self.assertEqual(p["consumer_number"], "1100000000001")
		self.assertEqual((p["section_code"], p["section_name"]), ("4321", "Testpuram"))
		self.assertEqual(p["name"], "ANNA VARGHESE")
		# The address does not repeat the name, and a line cut at the column's width runs on.
		self.assertEqual(p["address"], "HOUSE NO.1, PUTHENVEEDU LANE NEAR TEMPLE, KAKKANAD 682030")
		self.assertEqual(p["pincode"], "682030")
		self.assertEqual((p["tariff"], p["phase"]), ("LT-1", "Single"))
		self.assertEqual(p["connected_load_watts"], 4200)
		self.assertEqual(p["billing_frequency"], "Bimonthly")
		self.assertEqual(p["units"], 538)  # three ToD zones
		self.assertEqual(p["bill_amount"], 4210)
		self.assertEqual(p["bill_date"], "20-07-2026")

	def test_a_photo_read_loosely_still_reads(self):
		p = kseb_bill.parse(SPOT_BILL)
		self.assertEqual(p["consumer_number"], "1100000000002")
		self.assertEqual(p["name"], "MARY JOSEPH")
		self.assertEqual(p["connected_load_watts"], 3500)  # kW to watts
		self.assertEqual(p["phase"], "Single")
		self.assertEqual(p["billing_frequency"], "Monthly")
		self.assertEqual(p["units"], 180)
		self.assertEqual(p["bill_amount"], 1250)

	def test_the_fields_of_a_customer_and_of_a_lead(self):
		p = kseb_bill.parse(EBILL)
		with patch.object(kseb_bill, "find_section", return_value=("SECT-1", "DISCOM-1")), \
				patch("a3_sola.solar_crm.doctype.kseb_tariff_category.kseb_tariff_category.kseb_code", return_value="LT-I"):
			consumer, warnings = kseb_bill.to_fields(p, "Solar Consumer")
			lead, _ = kseb_bill.to_fields(p, "Lead")
		self.assertEqual(warnings, [])
		self.assertEqual(consumer["consumer_name"], "Anna Varghese")
		self.assertEqual((consumer["discom"], consumer["discom_section"], consumer["tariff_category"]), ("DISCOM-1", "SECT-1", "LT-I"))
		self.assertEqual(consumer["connection_type"], "Single Phase")
		self.assertEqual((consumer["avg_consumption_units"], consumer["avg_bill_amount"]), (538, 4210))
		self.assertEqual(consumer["site_address_line1"], "HOUSE NO.1")
		self.assertEqual(consumer["site_pincode"], "682030")
		# A lead's bill is monthly: a two-month bill is halved; it has no address lines.
		self.assertEqual(lead["avg_monthly_bill"], 2105)
		self.assertEqual(lead["lead_name"], "Anna Varghese")
		self.assertNotIn("site_address_line1", lead)

	def test_an_unknown_section_is_a_warning_not_a_guess(self):
		with patch.object(kseb_bill, "find_section", return_value=(None, None)), \
				patch.object(kseb_bill, "kseb_discom", return_value="DISCOM-1"):
			fields, warnings = kseb_bill.to_fields({"section_code": "9999", "section_name": "Nowhere"}, "Lead")
		self.assertNotIn("discom_section", fields)
		self.assertEqual(fields["discom"], "DISCOM-1")
		self.assertIn("9999", warnings[0])

	def test_a_section_code_counts_only_with_its_name(self):
		rows = [frappe._dict(name="S-A", discom="D", section_name="Alappuzha Town"),
			frappe._dict(name="S-B", discom="D", section_name="Testpuram")]
		with patch.object(frappe, "get_all", side_effect=lambda dt, filters, fields: rows if "section_code" in filters else []):
			self.assertEqual(kseb_bill.find_section({"section_code": "4321", "section_name": "Testpuram"}), ("S-B", "D"))
			self.assertEqual(kseb_bill.find_section({"section_code": "4321", "section_name": "Elsewhere"}), (None, None))

	def test_a_pdf_is_read_from_its_text(self):
		from frappe.utils.pdf import get_pdf

		pdf = get_pdf("<pre style='font-family:monospace;font-size:8px'>" + frappe.utils.escape_html(EBILL) + "</pre>")
		text, source = kseb_bill.extract_text(pdf, "bill.pdf")
		self.assertEqual(source, "pdf-text")
		self.assertEqual(kseb_bill.parse(text)["consumer_number"], "1100000000001")

	def test_a_photo_without_ocr_says_so(self):
		with patch.object(kseb_bill, "tesseract", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				kseb_bill.extract_text(b"\x89PNG\r\n\x1a\n" + b"0" * 64, "bill.png")

	@unittest.skipUnless(kseb_bill.tesseract(), "Tesseract is not installed")
	def test_a_photo_is_read_with_ocr(self):
		import io

		from PIL import Image, ImageDraw

		image = Image.new("RGB", (1400, 500), "white")
		draw = ImageDraw.Draw(image)
		for i, line in enumerate(SPOT_BILL.strip().split("\n")[:4]):
			draw.text((40, 30 + i * 40), line, fill="black")
		buf = io.BytesIO()
		image.save(buf, "PNG")
		text, source = kseb_bill.extract_text(buf.getvalue(), "bill.png")
		self.assertEqual(source, "ocr")
		self.assertIn("1100000000002", text.replace(" ", ""))

	def test_only_a_lead_or_customer(self):
		with self.assertRaises(frappe.ValidationError):
			kseb_bill.read("Quotation")
