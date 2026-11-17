# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A lead's Next steps offer the site survey, the subsidy eligibility check and the design
proposal as well as the customer, each filled from whatever the lead knows
(api/portal_chain.CHAIN["Lead"]). The survey needs a customer, so that step makes one from
the lead first and then opens the survey's create form."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_chain, portal_crud
from a3_sola.tests.fixtures import make_lead


def lead_with(**values):
	name = make_lead(lead_name="Next Steps")
	frappe.db.set_value("Lead", name, {"consumer_number": None, **values})
	return frappe.get_doc("Lead", name)


class TestLeadNextSteps(FrappeTestCase):
	def test_the_lead_offers_all_four_steps_in_order(self):
		steps = portal_chain.steps_for(lead_with())
		self.assertEqual([s["key"] for s in steps], ["consumer", "survey", "eligibility", "estimate"])
		by_key = {s["key"]: s for s in steps}
		self.assertTrue(by_key["survey"]["posts"])
		self.assertIn("customer record", by_key["survey"]["note"])
		self.assertFalse(by_key["eligibility"]["posts"])
		self.assertIn("source_dt=Lead", by_key["eligibility"]["create_route"])
		self.assertIn("/design-estimates/new?source_dt=Lead", by_key["estimate"]["create_route"])
		self.assertFalse(any(s["blocked"] for s in steps))

	def test_the_survey_step_makes_the_customer_and_opens_the_form(self):
		lead = lead_with(mobile_no="9000000011")
		out = portal_crud.create_mapped(slug="site-surveys", source_dt="Lead", source=lead.name)
		self.assertTrue(out["route"].startswith("/a3solaportal/site-surveys/new?source_dt=Lead&source="))
		consumer = frappe.db.get_value("Lead", lead.name, "solar_consumer")
		self.assertTrue(consumer)
		self.assertEqual(frappe.db.get_value("Solar Consumer", consumer, "lead"), lead.name)
		# The form is filled from the lead and the customer it now has.
		lead.reload()
		values = portal_chain.mapped_values(portal_chain.find_step("Lead", "site-surveys"), lead)
		self.assertEqual(values["lead"], lead.name)
		self.assertEqual(values["solar_consumer"], consumer)
		self.assertEqual(values["customer_name"], "Next Steps")
		self.assertEqual(values["contact_no"], "9000000011")
		# A second click keeps the same customer.
		portal_crud.create_mapped(slug="site-surveys", source_dt="Lead", source=lead.name)
		self.assertEqual(frappe.db.get_value("Lead", lead.name, "solar_consumer"), consumer)

	def test_the_eligibility_check_takes_what_the_lead_knows(self):
		lead = lead_with(mobile_no="9000000022", approx_capacity_kw=4, avg_monthly_bill=3200,
			approx_consumption_units=450, connection_type="Single Phase")
		values = portal_chain.mapped_values(portal_chain.find_step("Lead", "subsidy-eligibility"), lead)
		self.assertEqual(values["lead"], lead.name)
		self.assertEqual(values["consumer_name"], "Next Steps")
		self.assertEqual(values["mobile_no"], "9000000022")
		self.assertEqual(values["capacity_kw"], 4)
		self.assertEqual(values["avg_bill_amount"], 3200)
		self.assertEqual(values["avg_monthly_units"], 450)
		self.assertEqual(values["connection_type"], "Single Phase")
		self.assertNotIn("solar_consumer", values)

	def test_a_check_made_from_the_lead_becomes_its_card(self):
		lead = lead_with(approx_capacity_kw=3)
		scheme = lead.subsidy_scheme or frappe.db.get_value("Subsidy Scheme", {}, "name")
		out = portal_crud.create_record(slug="subsidy-eligibility", source_dt="Lead", source=lead.name,
			subsidy_scheme=scheme, check_date=frappe.utils.today())
		check = frappe.get_doc("Subsidy Eligibility Check", out["name"])
		self.assertEqual(check.lead, lead.name)
		self.assertEqual(check.consumer_name, "Next Steps")
		step = next(s for s in portal_chain.steps_for(lead) if s["key"] == "eligibility")
		self.assertTrue(step["done"])
		self.assertEqual(step["card"]["name"], check.name)
