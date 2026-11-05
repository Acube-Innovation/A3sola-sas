# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A dealer can be a lead's owner: Lead Owner lists the dealers to staff, and a dealer chosen
there becomes the lead's dealer, so he sees it (api/leads.owner_choices, overrides/lead)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import leads

DEALER = "test-owner-dealer@example.com"
OTHER_DEALER = "test-owner-dealer2@example.com"


def _dealer(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Owner Dealer", "send_welcome_email": 0,
			"role_profile_name": "Solar Dealer"}).insert(ignore_permissions=True)
	return email


def _lead(**extra):
	return frappe.get_doc({"doctype": "Lead", "lead_name": "Dealer Owner Test", "loan_required": "No", **extra}
		).insert(ignore_permissions=True)


class TestDealerAsLeadOwner(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.dealer, self.other = _dealer(DEALER), _dealer(OTHER_DEALER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_staff_see_dealers_in_lead_owner(self):
		lead = _lead()
		specs = {f["fieldname"]: f for s in leads.edit_fields(lead) for f in s["fields"]}
		owners = {c["value"]: c["label"] for c in specs["lead_owner"]["choices"]}
		self.assertIn(self.dealer, owners)
		self.assertTrue(owners[self.dealer].endswith("(Dealer)"))

	def test_a_dealer_as_owner_becomes_the_leads_dealer_and_sees_it(self):
		lead = _lead()
		leads.update_lead(lead.name, lead_owner=self.dealer, a3s_dealer="")
		self.assertEqual(frappe.db.get_value("Lead", lead.name, "a3s_dealer"), self.dealer)
		frappe.set_user(self.dealer)
		self.assertTrue(frappe.has_permission("Lead", "read", lead.name))

	def test_a_staff_owner_leaves_the_dealer_alone(self):
		lead = _lead(a3s_dealer=self.dealer)
		lead.lead_owner = frappe.db.get_value("User", {"user_type": "System User", "enabled": 1,
			"name": ["not in", ["Administrator", "Guest"]]}, "name")
		lead.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Lead", lead.name, "a3s_dealer"), self.dealer)

	def test_a_dealer_sees_no_other_dealers_in_lead_owner(self):
		lead = _lead(a3s_dealer=self.dealer)
		frappe.set_user(self.dealer)
		self.assertNotIn(self.other, [c["value"] for c in leads.owner_choices(lead)])
