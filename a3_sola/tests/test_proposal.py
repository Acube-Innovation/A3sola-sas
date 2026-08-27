# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal register - the client's spreadsheet, moved into ERPNext."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import outreach
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey


def make_proposal(estimate, consumer, **kwargs):
	values = {
		"doctype": "Solar Proposal",
		"company": consumer.company,
		"solar_consumer": consumer.name,
		"solar_design_estimate": estimate.name,
		"customer_name": consumer.consumer_name,
		"mobile_no": "9895778516",
		"location": "Chalakudy",
		"district": "Thrissur",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


class TestSolarProposal(FrappeTestCase):
	def setUp(self):
		self.consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		self.survey = make_survey(self.consumer, segments=((240, True),))
		self.estimate = make_estimate(self.consumer, self.survey, submit=True)

	def test_sequence_allocated_per_fiscal_year(self):
		first = make_proposal(self.estimate, self.consumer)
		second = make_proposal(self.estimate, self.consumer)
		self.assertEqual(second.proposal_sequence, first.proposal_sequence + 1)
		self.assertEqual(first.fiscal_year, second.fiscal_year)

	def test_name_uses_the_clients_existing_series(self):
		proposal = make_proposal(self.estimate, self.consumer)
		self.assertTrue(proposal.name.startswith("RENC-PROP-"))
		self.assertIn(proposal.fiscal_year.split("-")[0][-2:], proposal.name)

	def test_file_name_follows_the_clients_convention(self):
		"""sequence - series - date - capacity - customer, as they already file them."""
		proposal = make_proposal(self.estimate, self.consumer, customer_name="Shiju")
		self.assertTrue(proposal.proposal_file_name.startswith(f"{proposal.proposal_sequence}-RENC-PROP-"))
		self.assertTrue(proposal.proposal_file_name.endswith("-Shiju"))
		self.assertIn(proposal.capacity_label, proposal.proposal_file_name)

	def test_offer_details_pulled_from_the_estimate(self):
		proposal = make_proposal(self.estimate, self.consumer)
		self.assertEqual(proposal.capacity_kw, self.estimate.final_capacity_kw)
		self.assertEqual(proposal.options_quoted, len(self.estimate.options))
		self.assertEqual(proposal.statutory_total, self.estimate.statutory_total)
		self.assertEqual(proposal.capacity_label, "3Kw 1PH")

	def test_submitting_supersedes_the_previous_proposal(self):
		first = make_proposal(self.estimate, self.consumer)
		first.submit()
		second = make_proposal(self.estimate, self.consumer)
		second.submit()
		first.reload()
		self.assertEqual(first.status, "Superseded")
		self.assertEqual(first.superseded_by, second.name)

	def test_submit_advances_consumer_status(self):
		proposal = make_proposal(self.estimate, self.consumer)
		proposal.submit()
		self.assertEqual(frappe.db.get_value("Solar Consumer", self.consumer.name, "status"), "Proposed")


class TestOutreachMessaging(FrappeTestCase):
	def test_greeting_preserves_whatsapp_formatting(self):
		"""The client's copy uses asterisks for bold. Converting them breaks the paste."""
		template = frappe.db.get_value("Outreach Message Template", {"template_name": "Proposal Sent"}, "name")
		lead = frappe.get_doc(
			{"doctype": "Lead", "lead_name": "Dhanya Menon", "company": frappe.defaults.get_global_default("company")}
		).insert(ignore_permissions=True)
		message = outreach.render_message(template, lead)
		self.assertIn("Hi Dhanya,", message)
		self.assertIn("*Thank you for your interest", message)
		self.assertNotIn("<b>", message)
		self.assertNotIn("<strong>", message)

	def test_signature_and_links_come_from_settings(self):
		template = frappe.db.get_value("Outreach Message Template", {"template_name": "Proposal Sent"}, "name")
		lead = frappe.get_doc(
			{"doctype": "Lead", "lead_name": "Test Person", "company": frappe.defaults.get_global_default("company")}
		).insert(ignore_permissions=True)
		message = outreach.render_message(template, lead)
		self.assertIn("renewcoreinnovations", message)
		self.assertIn("Instagram", message)

	def test_whatsapp_link_normalises_the_number(self):
		link = outreach.whatsapp_link("9895778516", "hello there")
		self.assertTrue(link.startswith("https://wa.me/919895778516?text="))
		self.assertIn("hello%20there", link)
