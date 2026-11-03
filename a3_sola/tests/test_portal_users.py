# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's Users page: only an admin manages users; each kind gets its access, a
set-password link that works, and a delete that disables a user the records name
(api/portal_users)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_users as pu


def _new(kind, email, **extra):
	data = {"type": kind, "first_name": "Test", "last_name": kind, "email": email, "mobile_no": ""}
	data.update(extra)
	return pu.save_user(data)


class TestPortalUsers(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_only_an_admin_manages_users(self):
		_new("Dealer", "pu-dealer@example.com")
		_new("Employee", "pu-staff@example.com", profile="Solar Sales")
		for who in ("pu-dealer@example.com", "pu-staff@example.com"):
			frappe.set_user(who)
			self.assertFalse(pu.is_user_admin())
			with self.assertRaises(frappe.PermissionError):
				pu.users()
			with self.assertRaises(frappe.PermissionError):
				pu.delete_user("pu-dealer@example.com")
		frappe.set_user("Administrator")
		_new("Admin", "pu-admin@example.com")
		frappe.set_user("pu-admin@example.com")
		self.assertTrue(pu.is_user_admin())
		self.assertIn("pu-staff@example.com", [u["name"] for u in pu.users()["users"]])

	def test_each_kind_gets_its_access(self):
		_new("Employee", "pu-staff@example.com", profile="Solar Operations")
		self.assertEqual(frappe.db.get_value("User", "pu-staff@example.com", ["user_type", "role_profile_name"]),
			("System User", "Solar Operations"))
		company = pu._company()
		if company:
			self.assertTrue(frappe.db.exists("User Permission", {"user": "pu-staff@example.com", "allow": "Company", "for_value": company}))
		_new("Dealer", "pu-dealer@example.com")
		self.assertEqual(frappe.db.get_value("User", "pu-dealer@example.com", "user_type"), "Website User")
		made = _new("Contractor", "pu-con@example.com", new_contractor={"contractor_name": "PU Test Contractor", "contractor_type": "Electrical"})
		self.assertEqual(frappe.db.get_value("Solar Contractor", made["contractor"], "user"), "pu-con@example.com")
		kinds = {u["name"]: u["type"] for u in pu.users()["users"]}
		self.assertEqual((kinds["pu-staff@example.com"], kinds["pu-dealer@example.com"], kinds["pu-con@example.com"]),
			("Employee", "Dealer", "Contractor"))

	def test_a_duplicate_login_and_an_employee_without_access_are_refused(self):
		_new("Dealer", "pu-dealer@example.com")
		with self.assertRaises(frappe.ValidationError):
			_new("Dealer", "pu-dealer@example.com")
		with self.assertRaises(frappe.ValidationError):
			_new("Employee", "pu-noaccess@example.com")

	def test_an_admin_cannot_disable_himself(self):
		_new("Admin", "pu-admin@example.com")
		frappe.set_user("pu-admin@example.com")
		with self.assertRaises(frappe.ValidationError):
			pu.set_enabled("pu-admin@example.com", 0)

	def test_the_set_password_link_works_once(self):
		from frappe.core.doctype.user.user import _get_user_for_update_password

		_new("Dealer", "pu-dealer@example.com")
		link = pu.password_link("pu-dealer@example.com")["link"]
		self.assertIn("/a3solaportal/set-password?key=", link)
		key = link.split("key=")[1]
		self.assertEqual(_get_user_for_update_password(key, None).get("user"), "pu-dealer@example.com")

	def test_the_welcome_goes_by_whatsapp_and_says_when_email_cannot(self):
		_new("Dealer", "pu-dealer@example.com", mobile_no="9000000555")
		w = pu.welcome("pu-dealer@example.com", "whatsapp")
		self.assertTrue(w["whatsapp"].startswith("https://wa.me/919000000555?text="))
		self.assertIn("set-password", w["text"])
		from a3_sola.api.portal_share import _outgoing_account

		if not _outgoing_account("User"):
			with self.assertRaises(frappe.ValidationError):
				pu.welcome("pu-dealer@example.com", "email")

	def test_delete_removes_an_unused_user_and_disables_a_used_one(self):
		_new("Dealer", "pu-fresh@example.com")
		self.assertEqual(pu.delete_user("pu-fresh@example.com").get("deleted"), 1)
		self.assertFalse(frappe.db.exists("User", "pu-fresh@example.com"))
		_new("Dealer", "pu-used@example.com")
		frappe.get_doc({"doctype": "Lead", "first_name": "PU Lead", "mobile_no": "9000000666",
			"a3s_dealer": "pu-used@example.com"}).insert(ignore_permissions=True)
		r = pu.delete_user("pu-used@example.com")
		self.assertEqual((r.get("deleted"), r.get("disabled")), (0, 1))
		self.assertEqual(frappe.db.get_value("User", "pu-used@example.com", "enabled"), 0)

	def test_a_system_manager_is_an_admin_and_keeps_his_roles_when_edited(self):
		_new("Employee", "pu-sm@example.com", profile="Solar Sales")
		user = frappe.get_doc("User", "pu-sm@example.com")
		user.role_profile_name = None
		user.add_roles("System Manager")
		self.assertEqual(next(u["type"] for u in pu.users()["users"] if u["name"] == "pu-sm@example.com"), "Admin")
		pu.save_user({"type": "Admin", "first_name": "Renamed", "email": "pu-sm@example.com", "mobile_no": ""}, name="pu-sm@example.com")
		self.assertIn("System Manager", frappe.get_roles("pu-sm@example.com"))
		self.assertEqual(frappe.db.get_value("User", "pu-sm@example.com", "first_name"), "Renamed")
