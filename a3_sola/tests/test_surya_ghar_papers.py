# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar registration files the papers the portal gives back; the customer's own papers
are shown from the customer, on its Attachments card and on the task's documents."""

from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_attachments as pa
from a3_sola.api import portal_tasks as pt
from a3_sola.setup import seed_stages


class TestSuryaGharPapers(FrappeTestCase):
	def test_registration_offers_the_portal_papers_only(self):
		self.assertEqual(pa.offered_types("Portal Application", None, "any", "NPA"),
			["PM Surya Ghar Acknowledgement", "Feasibility Report", "E-Token", "Net Meter Agreement"])

	def test_other_applications_keep_their_types(self):
		self.assertEqual(pa.offered_types("Portal Application", None, "any", "CEIG"), list(pa.OFFERED["Portal Application"]))

	def test_customer_papers_are_not_offered(self):
		self.assertFalse(set(pa.SURYA_GHAR) & set(pa.CUSTOMER_PAPERS))

	def test_task_expects_the_portal_papers(self):
		expected = {name for name, _m, _t in seed_stages.checklists()["NPA"][1]}
		self.assertTrue({"Portal acknowledgement", "Feasibility Report", "E-Token", "Net Meter Agreement"} <= expected)

	def test_task_shows_the_customers_papers(self):
		self.assertEqual([label for label, _types in pt.SURYA_GHAR_CUSTOMER], ["Aadhaar", "PAN", "KSEB Bill", "Bank Proof"])
		types = {t for _label, kinds in pt.SURYA_GHAR_CUSTOMER for t in kinds}
		self.assertTrue(types <= set(pa.CUSTOMER_PAPERS))

	def test_jan_samarth_offers_the_approval_letter_only(self):
		self.assertEqual(pa.offered_types("Installation Task", None, "any", "DAL"), ["Digital Approval Letter"])
