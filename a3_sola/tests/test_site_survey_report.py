# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The site survey holds the team's paper Site Survey Report, and prints as it."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import survey_print
from a3_sola.tests.fixtures import make_consumer, make_survey


class TestSiteSurveyReport(FrappeTestCase):
	def setUp(self):
		self.consumer = make_consumer()
		self.survey = make_survey(self.consumer, segments=((240, True),), submit=False)

	def fill(self, **values):
		self.survey.update({"site_visit_for": "KSEB", "system_type": "On-grid", "parapet_available": 1,
			"parapet_height_cm": 90, "total_dc_length_m": 30, "dc_earthing_ground": "Soil", "supply_type": "LT",
			"incomer": "63A MCB", **values})
		self.survey.save(ignore_permissions=True)
		return self.survey

	def test_the_customer_comes_from_the_customer_record(self):
		self.assertEqual(self.survey.consumer_number, self.consumer.consumer_number)
		self.assertEqual(self.survey.contact_no, self.consumer.mobile_no)

	def test_answers_that_stand_with_another_are_cleared(self):
		survey = self.fill(parapet_available=0, supply_type="")
		self.assertFalse(survey.parapet_height_cm)
		self.assertFalse(survey.incomer)

	def test_the_customers_approval_is_named_and_dated(self):
		survey = self.fill(customer_approved=1)
		self.assertEqual(survey.customer_approval_name, survey.customer_name)
		self.assertTrue(survey.customer_approval_date)

	def test_it_prints_as_the_paper_report(self):
		survey = self.fill()
		text = " ".join(PdfReader(BytesIO(survey_print.render(survey)[1])).pages[0].extract_text().split())
		for expected in ("SITE SURVEY REPORT", "Height of parapet: 90", "63A MCB", "Cable length", "30 m"):
			self.assertIn(expected, text)

	def test_the_customer_can_approve_after_the_survey_is_filed(self):
		survey = self.fill()
		survey.submit()
		survey.reload()
		survey.customer_approved = 1
		survey.save(ignore_permissions=True)
		self.assertEqual(survey.customer_approval_name, survey.customer_name)
