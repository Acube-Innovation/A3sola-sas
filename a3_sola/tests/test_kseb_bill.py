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


# A bill on a non-ToD meter: one Cumulative zone, a short address, a name in initials.
CUMULATIVE_BILL = """
Section              [1234]-Electrical Section Testoor                                           Phone#            0480-0000000
Consumer#            1100000000003                                          Reg. Mob# 900xxxx000
Name & Mailing Address                                                      For redressing complaints/grievance approach the concerned CGRF

KP RAJAN                                                                    South: Chairperson,CGRF(South),KSEBL,Vydyuthi Bhavanam, Kottarakkara-691506, Ph:0474-2451300

PUTHUR H, P O TESTNAGAR,TESTOOR                                             Central: Chairperson,CGRF(Central),KSEBL,220KV SubStation,Kalamassery-683503,Ph:0484-2556500

Bill#                             1234260903708                                Bill Area                A03/9
Billing Period                    9/2026[Bi-Monthly]                           Tariff/Phase             LT-1/Single         Pole#                      MMR-1/3
Bill Date                         09-09-2026                                   Due Date                 19-09-2026
Contract Demand                   (Nil) VA [75% : 0KV, 130% : 0KV]             Connected Load           3728 Watts
            KWH                         Cumulative                Import                 17284.00                  17499.00                    1                                215
                                                                                                   e)   Total Amt.(Bill#1234260903708)      (a+b+c+d)                       1015.00
"""


# An e-bill photographed and read by OCR: table borders as "|", labels missing their first
# letter, the consumer number split, lines running on into the CGRF column.
OCR_EBILL = """Section [1234]-Electrical Section Testoor Phone# _[o480-0000000 Customer Care |i 912
consumert 1 100000000004 Reg. Mob# 900xxxx000 Regular CC Bill(PostPaid) | KSEBL GSTIN: 32AAECK2277NBZ1
Name & Mailing Address
KP RAJAN South: Chairperson,cgrf(south),ksebl,vydyuthi Bhavanam, Kottarakkara-691506, Ph:0474-2451300
PUTHUR H, P O TESTNAGAR tion, Kalamassery-683503, Ph:0484-2556500
Bill# 1234260903708 Bill Area A03/9
Billing Period 9/2026[Bi-Monthly] ariff/Phase LT-1/Single |Pole# IMMR-106/3
Contract Demand Nil) VA [75% : OKV, 130% : OKV] onnected Load 3728 Watts ecurity Deposit Rs.2046.00
KWH Cumulative Import 17284.00 17499.00 | 1 | 215
e) otal Amt.(Bill#1234260903708) (a+b+c+d) 1015.00
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

	def test_a_bill_on_a_cumulative_meter(self):
		p = kseb_bill.parse(CUMULATIVE_BILL)
		self.assertEqual(p["units"], 215)
		self.assertEqual(p["address"], "PUTHUR H, P O TESTNAGAR,TESTOOR")
		self.assertEqual(p["bill_amount"], 1015)
		self.assertEqual(kseb_bill.name_case(p["name"]), "KP Rajan")
		self.assertEqual(kseb_bill.name_case("ANNA VARGHESE"), "Anna Varghese")

	def test_a_photographed_ebill_reads_past_ocr_noise(self):
		p = kseb_bill.parse(OCR_EBILL)
		self.assertEqual(p["consumer_number"], "1100000000004")
		self.assertEqual(p["name"], "KP RAJAN")
		# The CGRF column beside it is not the customer's address (nor its PIN).
		self.assertEqual(p["address"], "PUTHUR H, P O TESTNAGAR")
		self.assertNotIn("pincode", p)
		self.assertEqual((p["tariff"], p["phase"]), ("LT-1", "Single"))
		self.assertEqual(p["connected_load_watts"], 3728)
		self.assertEqual(p["units"], 215)
		self.assertEqual(p["bill_amount"], 1015)

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
