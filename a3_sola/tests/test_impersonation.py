# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
""""Log in as" (api/impersonation): who may log in as whom, and the clock.

The switch itself is Frappe's (login_manager.impersonate) and needs a real request, so it was
checked over HTTP; these hold the rules around it.

Never run on the dev site: `bench run-tests` there wipes Item Prices (ERPNext before_tests).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from a3_sola.api import console, impersonation, memberships
from a3_sola.api import portal_users as pu
from a3_sola.tests.test_memberships import ALI, MembershipCase


class TestWhoMay(MembershipCase):
	def _dealer(self, email="test-imp-dealer@example.com"):
		frappe.set_user(self.a_admin)
		pu.save_user({"type": "Dealer", "first_name": "Dee", "email": email, "mobile_no": ""})
		frappe.set_user("Administrator")
		return email

	def test_a_company_admin_may_log_in_as_his_own_dealer(self):
		dealer = self._dealer()
		level, company, _why = impersonation.can_impersonate(self.a_admin, dealer)
		self.assertEqual((level, company), ("Company Admin", self.a))

	def test_but_not_as_another_admin(self):
		other = self._admin("test-imp-admin2@example.com", self.a)
		self.assertIsNone(impersonation.can_impersonate(self.a_admin, other)[0])

	def test_nor_as_someone_who_also_works_in_another_company(self):
		self.assertIsNone(impersonation.can_impersonate(self.a_admin, ALI)[0])

	def test_nor_as_someone_of_another_company(self):
		dealer = self._dealer()
		self.assertIsNone(impersonation.can_impersonate(self.b_admin, dealer)[0])

	def test_nor_as_himself_or_platform_staff(self):
		self.assertIsNone(impersonation.can_impersonate(self.a_admin, self.a_admin)[0])
		self.assertIsNone(impersonation.can_impersonate(self.a_admin, "Administrator")[0])

	def test_platform_staff_may_log_in_as_anyone_in_any_of_his_companies(self):
		self.assertEqual(impersonation.can_impersonate("Administrator", ALI, self.b)[:2], ("Platform", self.b))

	def test_a_dealer_may_log_in_as_nobody(self):
		dealer = self._dealer()
		self.assertIsNone(impersonation.can_impersonate(dealer, "test-imp-other@example.com")[0])

	def test_minutes_are_capped_per_level(self):
		self.assertEqual(impersonation.minutes_for("Company Admin", 999), 60)
		self.assertEqual(impersonation.minutes_for("Platform", 999), 120)
		self.assertEqual(impersonation.minutes_for("Platform", 1), 5)


class TestTheClock(MembershipCase):
	def _session(self, target, minutes=30, status="Open"):
		return frappe.get_doc({"doctype": impersonation.DOCTYPE, "operator": self.a_admin, "target": target,
			"company": self.a, "level": "Company Admin", "status": status, "reason": "Checking a dealer's view",
			"started_on": now_datetime(), "expires_on": add_to_date(now_datetime(), minutes=minutes),
			"sid_hash": "x"}).insert(ignore_permissions=True)

	def test_a_person_with_an_open_session_cannot_be_logged_in_as_twice(self):
		frappe.set_user(self.a_admin)
		pu.save_user({"type": "Dealer", "first_name": "Dee", "email": "test-imp-twice@example.com", "mobile_no": ""})
		frappe.set_user("Administrator")
		self._session("test-imp-twice@example.com")
		self.assertIsNone(impersonation.can_impersonate(self.a_admin, "test-imp-twice@example.com")[0])

	def test_a_session_past_its_time_is_closed_and_audited(self):
		row = self._session(ALI, minutes=-1)
		before = frappe.db.count("Platform Audit Entry", {"entry_type": "Support Session Expired"})
		impersonation.expire_stale()
		self.assertEqual(frappe.db.get_value(impersonation.DOCTYPE, row.name, "end_reason"), "Expired")
		self.assertEqual(frappe.db.count("Platform Audit Entry", {"entry_type": "Support Session Expired"}), before + 1)

	def test_he_cannot_switch_company_while_someone_is_logged_in_as_him(self):
		self._session(ALI)
		frappe.set_user(ALI)
		with self.assertRaises(frappe.ValidationError):
			memberships.switch_company(self.b)


class TestConsole(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_a_companys_own_system_manager_cannot_open_a_support_session(self):
		"""System Manager used to be enough - and a company's own admin may hold it."""
		email = "test-tenant-sysmgr@example.com"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Sys", "send_welcome_email": 0,
			"roles": [{"role": "System Manager"}]}).insert(ignore_permissions=True)
		tenant = frappe.db.get_value("Tenant", {"admin_user": ["is", "set"]}, "name") or "any"
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			console.start_impersonation(tenant, "A long enough reason for the test")
