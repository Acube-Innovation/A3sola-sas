# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One login, several companies, a different role in each (api/memberships).

Ali is a Dealer at one company and the Admin of another. Whichever company he is working
in, he holds exactly that company's roles and sees exactly that company's records; the
admin of either company can change only his access there.

Never run on the dev site: `bench run-tests` there wipes Item Prices (ERPNext before_tests).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import memberships, partner_scope
from a3_sola.api import portal_users as pu
from a3_sola.api.permissions import get_permitted_companies
from a3_sola.api.tenant_users import _set_default_company, ensure_company_permission

ALI = "test-ali-shared@example.com"
B_ADMIN = "test-b-admin@example.com"
AUTOMATIC = {"All", "Guest", "Desk User"}


def _company(name, abbr):
	if frappe.db.exists("Company", name):
		return name
	doc = frappe.get_doc({"doctype": "Company", "company_name": name, "abbr": abbr,
		"default_currency": "INR", "country": "India"})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _roles(user):
	return set(frappe.get_roles(user)) - AUTOMATIC


class MembershipCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("A3 Sola Settings", "allow_shared_logins", 1)
		self.a = _company("Test Membership Alpha", "TMA")
		self.b = _company("Test Membership Beta", "TMB")
		self.a_admin = self._admin("test-a-admin@example.com", self.a)
		self.b_admin = self._admin(B_ADMIN, self.b)
		frappe.set_user(self.a_admin)
		pu.save_user({"type": "Dealer", "first_name": "Ali", "last_name": "Shared", "email": ALI, "mobile_no": ""})
		frappe.set_user(self.b_admin)
		pu.save_user({"type": "Admin", "first_name": "Ignored", "email": ALI})
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _admin(self, email, company):
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Admin", "send_welcome_email": 0,
				"role_profile_name": pu.ADMIN_PROFILE}).insert(ignore_permissions=True)
		ensure_company_permission(email, company)
		_set_default_company(email, company)
		memberships.record_current(email, company, "Admin")
		return email


class TestSwitching(MembershipCase):
	def test_he_starts_as_a_dealer_where_he_was_made(self):
		self.assertEqual(memberships.active_company(ALI), self.a)
		self.assertEqual(get_permitted_companies(ALI), [self.a])
		self.assertEqual(partner_scope.partner_kind(ALI), "dealer")
		self.assertFalse(pu.is_user_admin(ALI))
		self.assertEqual(frappe.db.get_value("User", ALI, "user_type"), "Website User")

	def test_switching_gives_the_other_companys_role_and_only_its_records(self):
		frappe.set_user(ALI)
		memberships.switch_company(self.b)
		frappe.set_user("Administrator")
		self.assertEqual(get_permitted_companies(ALI), [self.b])
		self.assertEqual(frappe.defaults.get_user_default("Company", user=ALI), self.b)
		self.assertIsNone(partner_scope.partner_kind(ALI))
		self.assertTrue(pu.is_user_admin(ALI))
		self.assertNotIn(partner_scope.DEALER, _roles(ALI))
		self.assertEqual(frappe.db.get_value("User", ALI, "user_type"), "System User")
		# And back: a dealer again, with none of the admin's roles left over.
		frappe.set_user(ALI)
		memberships.switch_company(self.a)
		frappe.set_user("Administrator")
		self.assertEqual(_roles(ALI), {partner_scope.DEALER})
		self.assertEqual(frappe.db.get_value("User", ALI, "user_type"), "Website User")
		self.assertEqual(get_permitted_companies(ALI), [self.a])

	def test_a_company_he_does_not_work_in_is_refused(self):
		frappe.set_user(ALI)
		with self.assertRaises(frappe.DoesNotExistError):
			memberships.switch_company(frappe.db.get_single_value("Global Defaults", "default_company") or "Nope")

	def test_a_role_given_another_way_is_taken_off_again(self):
		"""ERPNext gives Employee back whenever an Employee record is saved; for a dealer that
		would make him staff (partner_scope.STAFF_ROLES) and show him every lead."""
		user = frappe.get_doc("User", ALI)
		user.append_roles("Employee")
		user.save(ignore_permissions=True)
		self.assertNotIn("Employee", _roles(ALI))
		self.assertEqual(partner_scope.partner_kind(ALI), "dealer")

	def test_protected_roles_survive_a_switch(self):
		frappe.get_doc({"doctype": "Has Role", "parent": ALI, "parenttype": "User", "parentfield": "roles",
			"role": "Platform Sales"}).db_insert()
		frappe.clear_cache(user=ALI)
		memberships.apply_membership(ALI, self.b)
		self.assertIn("Platform Sales", _roles(ALI))
		self.assertFalse(frappe.db.get_value("User", ALI, "role_profile_name"))

	def test_sign_in_moves_off_a_disabled_company(self):
		memberships.apply_membership(ALI, self.b)
		frappe.db.set_value("Company Membership", {"user": ALI, "company": self.b}, "enabled", 0)
		self.assertEqual(memberships.pick_default(ALI), self.a)


class TestTheOtherAdmin(MembershipCase):
	def test_his_login_is_his_own(self):
		self.assertEqual(frappe.db.get_value("User", ALI, "first_name"), "Ali")
		frappe.set_user(self.b_admin)
		row = next(u for u in pu.users()["users"] if u["name"] == ALI)
		self.assertEqual((row["type"], row["shared"]), ("Admin", True))
		for refused in (pu.password_link, pu.welcome):
			with self.assertRaises(frappe.ValidationError):
				refused(ALI)
		with self.assertRaises(frappe.ValidationError):
			pu.set_password(ALI, "A-long-enough-password-1")

	def test_each_admin_sees_his_type_in_their_company(self):
		frappe.set_user(self.a_admin)
		row = next(u for u in pu.users()["users"] if u["name"] == ALI)
		self.assertEqual(row["type"], "Dealer")
		self.assertNotIn(B_ADMIN, [u["name"] for u in pu.users()["users"]])

	def test_disabling_or_removing_him_in_one_company_leaves_the_other(self):
		frappe.set_user(self.b_admin)
		pu.set_enabled(ALI, 0)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.get_value("User", ALI, "enabled"))
		self.assertEqual(memberships.active_company(ALI), self.a)
		frappe.set_user(self.b_admin)
		pu.delete_user(ALI)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("User", ALI))
		self.assertEqual([m.company for m in memberships.memberships(ALI, enabled_only=False)], [self.a])

	def test_removing_the_company_he_works_in_moves_him(self):
		memberships.apply_membership(ALI, self.b)
		frappe.set_user(self.b_admin)
		pu.delete_user(ALI)
		frappe.set_user("Administrator")
		self.assertEqual(memberships.active_company(ALI), self.a)
		self.assertEqual(get_permitted_companies(ALI), [self.a])

	def test_an_instance_wide_account_is_never_shared(self):
		staff = "test-platform-staff@example.com"
		frappe.get_doc({"doctype": "User", "email": staff, "first_name": "Staff", "send_welcome_email": 0,
			"roles": [{"role": "Platform Sales"}]}).insert(ignore_permissions=True)
		ensure_company_permission(staff, self.a)
		frappe.set_user(self.b_admin)
		with self.assertRaises(frappe.ValidationError) as caught:
			pu.save_user({"type": "Admin", "first_name": "X", "email": staff})
		self.assertIn("instance-wide", str(caught.exception))


class TestSingleCompanyLogins(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_a_login_in_one_company_keeps_its_membership_in_step(self):
		email = "test-single-membership@example.com"
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not company:
			self.skipTest("No default company.")
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "One", "send_welcome_email": 0,
			"role_profile_name": pu.DEALER_PROFILE}).insert(ignore_permissions=True)
		ensure_company_permission(email, company)
		memberships.record_current(email, company, "Dealer")
		user = frappe.get_doc("User", email)
		user.role_profile_name = None
		user.append_roles("Solar Contractor Partner")
		user.save(ignore_permissions=True)
		m = memberships.get_membership(email, company)
		self.assertIn("Solar Contractor Partner", [r.role for r in m.roles])
		self.assertIn("Solar Contractor Partner", _roles(email))
