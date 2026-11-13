# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The lead page's About card tells the lead in a paragraph, built only from what the lead has."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api.leads import lead_story
from a3_sola.tests.fixtures import make_lead


class TestLeadStory(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_a_thin_lead_reads_as_a_short_paragraph(self):
		doc = frappe.get_doc("Lead", make_lead(lead_name="Story Thin"))
		text = lead_story(doc)
		self.assertIn("Story Thin came in", text)
		self.assertIn("the record was made by", text)
		self.assertIn("no phone number or email yet", text)
		self.assertIn("None of their KYC papers are in yet.", text)
		self.assertNotIn("None.", text.replace("None of", ""))
		self.assertNotIn("  ", text)

	def test_a_full_lead_names_each_fact_once(self):
		doc = frappe.get_doc("Lead", make_lead(lead_name="Story Full"))
		doc.update({"mobile_no": "9000000077", "email_id": "story@example.com", "city": "Kollam",
			"state": "Kerala", "approx_capacity_kw": 3, "connection_type": "Single Phase",
			"consumer_category": "Residential", "consumer_number": "1156466", "loan_required": "Yes",
			"last_message_date": "2026-11-11", "next_followup_date": "2026-11-13",
			"solar_lead_status": "In Discussion", "outreach_stage": "Step 2: 24hr Nudge"})
		doc.flags.ignore_permissions = True
		doc.save()
		text = lead_story(frappe.get_doc("Lead", doc.name))
		self.assertIn("from Kollam, Kerala", text)
		self.assertIn("reach them on 9000000077 or story@example.com", text)
		self.assertIn("3 kW (Single Phase, residential); their consumer number is 1156466.", text)
		self.assertIn("They need a loan.", text)
		self.assertIn("We last connected on Nov 11, 2026, the lead is in discussion at Step 2: 24hr Nudge, "
			"with the next follow-up planned for Nov 13, 2026", text)
		self.assertEqual(text.count("Kerala"), 1)
