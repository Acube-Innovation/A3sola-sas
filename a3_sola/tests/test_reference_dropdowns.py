# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Whoever has a form open sees its reference dropdowns filled - districts, DISCOMs, sources -
whatever his role may read of those lists; a partner does not, and a company's own lists
stay its own (api/portal_fields.link_choices, is_open_reference)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_fields
from a3_sola.api.portal_fields import is_open_reference, link_choices

STAFF = "test-ref-coordinator@example.com"
DEALER = "test-ref-dealer@example.com"


def _user(email, profile):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Ref", "send_welcome_email": 0,
			"role_profile_name": profile}).insert(ignore_permissions=True)
	return email


def _no_read(*names):
	"""frappe.has_permission, with read refused on these doctypes - a role never given them."""
	real = frappe.has_permission

	def fake(doctype=None, ptype="read", *args, **kwargs):
		if doctype in names:
			return False
		return real(doctype, ptype, *args, **kwargs)

	return patch.object(portal_fields.frappe, "has_permission", side_effect=fake)


class TestReferenceDropdowns(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.staff, self.dealer = _user(STAFF, "Solar Sales Coordination"), _user(DEALER, "Solar Dealer")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_staff_get_a_reference_list_their_role_cannot_read(self):
		if not frappe.db.count("Indian District"):
			self.skipTest("No districts on this site.")
		frappe.set_user(self.staff)
		with _no_read("Indian District"):
			self.assertTrue(link_choices("Indian District"))

	def test_a_partner_does_not(self):
		frappe.set_user(self.dealer)
		self.assertFalse(is_open_reference("Indian District"))
		with _no_read("Indian District"):
			self.assertEqual(link_choices("Indian District"), [])

	def test_records_that_are_not_reference_lists_stay_closed(self):
		frappe.set_user(self.staff)
		for doctype in ("Customer", "Solar Installation", "Coupon Code", "User"):
			self.assertFalse(is_open_reference(doctype), doctype)
		with _no_read("Solar Installation"):
			self.assertEqual(link_choices("Solar Installation"), [])

	def test_a_company_list_is_held_to_the_users_companies(self):
		frappe.set_user(self.staff)
		with _no_read("DISCOM"), patch("a3_sola.api.permissions.get_permitted_companies", return_value=["No Such Company"]):
			values = [c["value"] for c in link_choices("DISCOM")]
		companies = {frappe.db.get_value("DISCOM", v, "company") for v in values}
		self.assertTrue(companies <= {None, "", "No Such Company"}, companies)
		with _no_read("DISCOM"), patch("a3_sola.api.permissions.get_permitted_companies", return_value=[]):
			self.assertEqual(link_choices("DISCOM"), [])
