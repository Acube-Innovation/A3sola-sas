# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Administration > Menu (api/portal_menu): what an admin unticks is hidden from everyone's
menu, a group left empty goes, and the Menu page itself is always there."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_menu
from a3_sola.www.a3solaportal import NAV_GROUPS, nav_groups

LEAD = "/a3solaportal/leads"


def routes(user=None):
	return {i["route"] for g in nav_groups(user) for i in g["items"]}


class TestPortalMenu(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_an_item_hidden_is_gone_from_every_menu(self):
		self.assertIn(LEAD, routes())
		portal_menu.save([LEAD])
		self.assertNotIn(LEAD, routes())
		with patch("a3_sola.api.portal_users.is_user_admin", return_value=False):
			self.assertNotIn(LEAD, routes())
		self.assertFalse(next(i for g in portal_menu.menu() for i in g["items"] if i["route"] == LEAD)["shown"])
		portal_menu.save([])
		self.assertIn(LEAD, routes())

	def test_a_group_with_nothing_shown_is_not_shown(self):
		group = next(g for g in NAV_GROUPS if g["key"] == "stores-accounts")
		portal_menu.save([i["route"] for i in group["items"]])
		self.assertNotIn("stores-accounts", {g["key"] for g in nav_groups()})

	def test_the_menu_page_cannot_be_hidden_and_is_for_admins(self):
		portal_menu.save([portal_menu.ROUTE, LEAD])
		self.assertIn(portal_menu.ROUTE, routes())
		self.assertEqual(portal_menu.hidden(), {LEAD})
		with patch("a3_sola.api.portal_users.is_user_admin", return_value=False):
			self.assertNotIn(portal_menu.ROUTE, routes())

	def test_only_an_admin_saves_and_only_menu_items(self):
		with self.assertRaises(frappe.ValidationError):
			portal_menu.save(["/a3solaportal/not-a-page"])
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			portal_menu.save([LEAD])
