# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A partner - a dealer, a contractor - sees his own records and nothing of the company's own
business (api/partner_scope)."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import partner_scope, supplier_bill, tasks
from a3_sola.www.a3solaportal import nav_groups
from a3_sola.www.a3solaportal.collections import form_groups, partner_hidden

DEALER_USER = "test-dealer@example.com"
CONTRACTOR_USER = "test-contractor@example.com"


def _user(email, profile):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0, "role_profile_name": profile}).insert(ignore_permissions=True)
	return email


class TestPartnerAccess(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.jobs = frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name", limit=2)
		if len(self.jobs) < 2:
			raise unittest.SkipTest("Two projects are needed.")
		self.dealer, self.contractor = _user(DEALER_USER, "Solar Dealer"), _user(CONTRACTOR_USER, "Solar Contractor")
		mine, other = self.jobs
		consumer = frappe.db.get_value("Solar Installation", mine, "solar_consumer")
		frappe.db.set_value("Solar Consumer", consumer, "dealer", self.dealer)
		con = frappe.get_doc({"doctype": "Solar Contractor", "contractor_name": "Test Partner Contractor",
			"contractor_type": "Electrical", "is_active": 1, "user": self.contractor,
			"company": frappe.db.get_value("Solar Installation", mine, "company")}).insert(ignore_permissions=True)
		frappe.db.set_value("Solar Installation", mine, "electrical_contractor", con.name)
		frappe.db.set_value("Solar Installation", other, {"electrical_contractor": None})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_partners_are_told_from_staff(self):
		self.assertEqual(partner_scope.partner_kind(self.dealer), "dealer")
		self.assertEqual(partner_scope.partner_kind(self.contractor), "contractor")
		self.assertIsNone(partner_scope.partner_kind("Administrator"))

	def test_a_dealer_sees_only_his_customers_projects(self):
		mine, other = self.jobs
		frappe.set_user(self.dealer)
		seen = frappe.get_list("Solar Installation", pluck="name")
		self.assertIn(mine, seen)
		self.assertNotIn(other, seen)
		self.assertTrue(frappe.get_doc("Solar Installation", mine).has_permission("read"))
		self.assertFalse(frappe.get_doc("Solar Installation", mine).has_permission("write"))
		self.assertFalse(frappe.has_permission("Purchase Invoice", "read"))

	def test_a_lead_a_dealer_makes_is_his(self):
		frappe.set_user(self.dealer)
		lead = frappe.get_doc({"doctype": "Lead", "first_name": "Partner Test", "mobile_no": "9000000123"}).insert()
		self.assertEqual(lead.a3s_dealer, self.dealer)
		self.assertIn(lead.name, frappe.get_list("Lead", pluck="name"))
		frappe.set_user("Administrator")
		other = frappe.get_doc({"doctype": "Lead", "first_name": "Not His", "mobile_no": "9000000124"}).insert()
		frappe.set_user(self.dealer)
		self.assertNotIn(other.name, frappe.get_list("Lead", pluck="name"))

	def test_a_contractor_sees_only_the_projects_he_is_on(self):
		mine, other = self.jobs
		frappe.set_user(self.contractor)
		seen = frappe.get_list("Solar Installation", pluck="name")
		self.assertEqual(seen, [mine])
		self.assertFalse(frappe.has_permission("Purchase Invoice", "read"))
		with self.assertRaises(frappe.PermissionError):
			supplier_bill.state(mine)

	def test_a_contractor_completes_only_his_tasks(self):
		mine, _ = self.jobs
		inst = frappe.get_doc("Solar Installation", mine)
		given, other = inst.stages[0].stage_code, inst.stages[1].stage_code
		inst.set("task_assignees", [r for r in inst.task_assignees if r.stage_code not in (given, other)])
		inst.append("task_assignees", {"stage_code": given, "user": self.contractor})
		self.assertTrue(tasks.may_complete(inst, given, user=self.contractor))
		self.assertFalse(tasks.may_complete(inst, other, user=self.contractor))
		self.assertTrue(partner_scope.may_open_task(mine, "SERIAL", user=self.contractor))
		self.assertFalse(partner_scope.may_open_task(mine, "SUPINV", user=self.contractor))

	def test_a_partner_sees_no_cost_and_a_short_menu(self):
		frappe.set_user(self.contractor)
		hidden = partner_hidden(frappe.get_meta("Solar Installation"))
		self.assertIn("gross_contract_value", hidden)  # permission level 1
		shown = {df.fieldname for g in form_groups(frappe.get_meta("Solar Installation")) for s in g["sections"] for df in s["fields"]}
		self.assertFalse(shown & hidden)
		routes = {i["route"] for g in nav_groups() for i in g["items"]}
		self.assertIn("/a3solaportal/projects", routes)
		self.assertNotIn("/a3solaportal/purchase-invoices", routes)
		frappe.set_user("Administrator")
		self.assertEqual(partner_hidden(frappe.get_meta("Solar Installation")), set())
