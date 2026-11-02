# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Jan Samarth digital approval letter gives its task the sanction number and the date."""

from frappe.tests.utils import FrappeTestCase

from a3_sola.api import approval_letter

# The top of a digital sanction letter's text, with made-up details.
LETTER = """Congratulations
Anna Varghese
Digital Sanction for your application : ANS-SOLAR-10000001-2000002
Date : 28 October 2026

    Solar Rooftop Financing
    You have received a digital sanction from Canara Bank
"""


class TestApprovalLetter(FrappeTestCase):
	def test_the_letter_gives_the_reference_and_date(self):
		read = approval_letter.parse(LETTER)
		self.assertEqual(read, {"name": "Anna Varghese", "reference": "ANS-SOLAR-10000001-2000002", "date": "2026-10-28"})
		self.assertEqual(approval_letter.task_values(read),
			{"approval_reference": "ANS-SOLAR-10000001-2000002", "approval_received_on": "2026-10-28"})

	def test_ocr_spacing_and_other_date_forms(self):
		read = approval_letter.parse("Digital Sanction for your application: ANS - SOLAR - 10000001 - 2000002\nDate: 3 Nov, 2026")
		self.assertEqual(read, {"reference": "ANS-SOLAR-10000001-2000002", "date": "2026-11-03"})
		self.assertEqual(approval_letter.parse("Digital Sanction\nDate : 05/11/2026")["date"], "2026-11-05")

	def test_the_applicant_is_matched_to_the_customer(self):
		self.assertTrue(approval_letter.same_person("Manoj P", "P MANOJ"))
		self.assertTrue(approval_letter.same_person("CK Boban", "C.K. Boban"))
		self.assertTrue(approval_letter.same_person("Anna Varghese", "Anna"))
		self.assertFalse(approval_letter.same_person("Manoj P", "Shanal"))

	def test_another_document_gives_nothing(self):
		self.assertEqual(approval_letter.parse("KERALA STATE ELECTRICITY BOARD\nBill Date 20-07-2026"), {})
