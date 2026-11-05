# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A partner may be both a dealer and a contractor - he sells and installs. He reaches what
either kind gives him and nothing of the company's beyond it, and sees no price on a job he
only installs (api/partner_scope, api/portal_users, project_overview.hides_money)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import partner_scope
from a3_sola.api import portal_users as pu

BOTH = "test-both-partner@example.com"


class TestDealerWhoInstalls(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _make(self):
		return pu.save_user({"type": "Dealer", "also": 1, "first_name": "Both", "last_name": "Partner", "email": BOTH,
			"mobile_no": "", "new_contractor": {"contractor_name": "Both Partner Installs", "contractor_type": "Electrical"}})

	def test_saved_with_both_roles_and_a_contractor_record(self):
		made = self._make()
		self.assertFalse(frappe.db.get_value("User", BOTH, "role_profile_name"))
		roles = set(frappe.get_roles(BOTH))
		self.assertTrue({partner_scope.DEALER, partner_scope.CONTRACTOR} <= roles)
		self.assertEqual(frappe.db.get_value("Solar Contractor", made["contractor"], "user"), BOTH)
		row = next(u for u in pu.users()["users"] if u["name"] == BOTH)
		self.assertEqual((row["type"], row["also"]), ("Dealer", "Contractor"))
		self.assertEqual(partner_scope.partner_kinds(BOTH), {"dealer", "contractor"})
		# Unticked again: a dealer alone, his contractor record let go.
		pu.save_user({"type": "Dealer", "also": 0, "first_name": "Both", "email": BOTH, "mobile_no": ""}, name=BOTH)
		self.assertEqual(frappe.db.get_value("User", BOTH, "role_profile_name"), "Solar Dealer")
		self.assertFalse(frappe.db.exists("Solar Contractor", {"user": BOTH}))

	def test_he_reaches_his_sales_and_his_installs_and_no_other_job(self):
		jobs = frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2], "solar_consumer": ["is", "set"]},
			pluck="name", limit=3)
		if len(jobs) < 3:
			self.skipTest("Three projects are needed.")
		sold, installs, other = jobs
		made = self._make()
		consumer = frappe.db.get_value("Solar Installation", sold, "solar_consumer")
		frappe.db.set_value("Solar Consumer", consumer, "dealer", BOTH)
		frappe.db.set_value("Solar Installation", installs, "electrical_contractor", made["contractor"])
		for job in (sold, other):
			if frappe.db.get_value("Solar Installation", job, "electrical_contractor") == made["contractor"]:
				frappe.db.set_value("Solar Installation", job, "electrical_contractor", None)
		other_consumer = frappe.db.get_value("Solar Installation", other, "solar_consumer")
		if other_consumer in (consumer,) or frappe.db.get_value("Solar Installation", installs, "solar_consumer") == consumer:
			self.skipTest("The projects share a customer.")
		frappe.set_user(BOTH)
		seen = set(frappe.get_list("Solar Installation", pluck="name", limit_page_length=0))
		self.assertIn(sold, seen)
		self.assertIn(installs, seen)
		self.assertNotIn(other, seen)

		from a3_sola.www.a3solaportal.project_overview import hides_money

		self.assertFalse(hides_money(frappe.get_doc("Solar Installation", sold)))
		self.assertTrue(hides_money(frappe.get_doc("Solar Installation", installs)))

	def test_a_contractor_alone_still_sees_no_price_and_a_dealer_alone_does(self):
		from a3_sola.www.a3solaportal.project_overview import hides_money

		job = frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name", limit=1)
		if not job:
			self.skipTest("No project.")
		doc = frappe.get_doc("Solar Installation", job[0])
		for email, profile, hidden in (("test-only-contractor@example.com", "Solar Contractor", True),
				("test-only-dealer@example.com", "Solar Dealer", False)):
			if not frappe.db.exists("User", email):
				frappe.get_doc({"doctype": "User", "email": email, "first_name": "Only", "send_welcome_email": 0,
					"role_profile_name": profile}).insert(ignore_permissions=True)
			frappe.set_user(email)
			self.assertEqual(hides_money(doc), hidden, profile)
			frappe.set_user("Administrator")
