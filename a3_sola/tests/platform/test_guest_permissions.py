# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The guest permission allowlist.

This app has one public website and four modules of private business data on the same
instance. Exactly six doctypes may be readable by a logged-out visitor. Everything else -
today and in every phase after this one - must not be.

As Phases 5 to 8 add doctypes to this same app, THIS is the test that stops one of them
becoming world-readable because a permission row was copied from the wrong template.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.registry import platform as platform_registry

#: The only doctypes a logged-out visitor may read, and why.
GUEST_READABLE = {
	"Platform Feature": "rendered on the homepage and its own detail page",
	"Platform Solution": "rendered on the homepage and its own detail page",
	"Platform Integration": "rendered in the integrations section",
	"Platform Stat": "rendered in the stat strip",
	"Platform FAQ": "rendered on the pricing page",
	"Subscription Plan": "rendered in the pricing section",
	"Platform Legal Page": "rendered at /legal/*",
	# Child tables of the above. A child is only reachable through its parent.
	"Platform Bullet": "child of Platform Feature and Platform Solution",
	"Platform Detail Section": "child of the content doctypes",
	"Plan Feature": "child of Subscription Plan",
	"Plan Module": "child of Subscription Plan",
}

#: Anything a guest holds beyond read is wrong, on any doctype at all.
FORBIDDEN_FOR_GUEST = ("write", "create", "delete", "submit", "cancel", "amend")

APP_MODULES = ("Solar CRM", "Solar Operations", "Solar Projects", "Platform")


def app_doctypes():
	return frappe.get_all(
		"DocType", filters={"module": ["in", APP_MODULES]}, pluck="name"
	)


def guest_rows(doctype):
	return [row for row in frappe.get_meta(doctype).permissions if row.role == "Guest"]


class TestGuestAllowlist(FrappeTestCase):
	def test_no_doctype_outside_the_allowlist_is_guest_readable(self):
		leaked = []
		for doctype in app_doctypes():
			if doctype in GUEST_READABLE:
				continue
			for row in guest_rows(doctype):
				if row.read:
					leaked.append(doctype)
					break
		self.assertEqual(
			leaked,
			[],
			f"these are readable by a logged-out visitor and should not be: {leaked}",
		)

	def test_a_guest_can_never_write_anything(self):
		writable = []
		for doctype in app_doctypes():
			for row in guest_rows(doctype):
				for ptype in FORBIDDEN_FOR_GUEST:
					if row.get(ptype):
						writable.append(f"{doctype}.{ptype}")
		self.assertEqual(writable, [], f"guest holds write-like permissions: {writable}")

	def test_the_allowlist_itself_is_all_platform_content(self):
		"""Nothing tenant-owned may drift onto the allowlist."""
		for doctype in GUEST_READABLE:
			module = frappe.db.get_value("DocType", doctype, "module")
			self.assertEqual(
				module, "Platform", f"{doctype} is on the guest allowlist but is not Platform content"
			)

	def test_every_allowlisted_doctype_actually_exists(self):
		for doctype in GUEST_READABLE:
			self.assertTrue(frappe.db.exists("DocType", doctype), f"{doctype} does not exist")

	def test_the_funnel_is_not_guest_readable(self):
		for doctype in platform_registry.FUNNEL_DOCTYPES:
			self.assertNotIn(doctype, GUEST_READABLE)
			for row in guest_rows(doctype):
				self.assertFalse(row.read, f"a guest can read {doctype}")

	def test_the_solar_modules_expose_nothing_to_guests(self):
		"""Three phases of tenant business data, none of it public."""
		exposed = []
		for doctype in frappe.get_all(
			"DocType",
			filters={"module": ["in", ["Solar CRM", "Solar Operations", "Solar Projects"]]},
			pluck="name",
		):
			if any(row.read for row in guest_rows(doctype)):
				exposed.append(doctype)
		self.assertEqual(exposed, [], f"tenant data readable by a guest: {exposed}")


class TestGuestCannotReachDataInPractice(FrappeTestCase):
	"""Permission rows are the theory. This is what actually happens."""

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_guest_can_list_published_plans(self):
		frappe.set_user("Guest")
		plans = frappe.get_list("Subscription Plan", fields=["plan_code"], ignore_permissions=False)
		self.assertTrue(plans, "the pricing section cannot render without this")

	def test_a_guest_cannot_list_a_solar_installation(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Solar Installation", ignore_permissions=False)

	def test_a_guest_cannot_list_a_project(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Solar Billing Plan", ignore_permissions=False)

	def test_a_guest_cannot_read_the_settings_singleton(self):
		"""It holds the captcha secret and every naming series in the product."""
		frappe.set_user("Guest")
		self.assertFalse(
			frappe.has_permission("A3 Sola Settings", "read", user="Guest"),
			"a guest can read A3 Sola Settings",
		)

	def test_a_guest_cannot_read_a_platform_legal_page_that_is_unpublished(self):
		frappe.db.set_value("Platform Legal Page", "terms", "is_published", 0)
		frappe.clear_cache()
		try:
			frappe.set_user("Guest")
			from frappe.utils import set_request
			from frappe.website.serve import get_response

			set_request(method="GET", path="/legal/terms")
			self.assertEqual(get_response("/legal/terms").status_code, 404)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Platform Legal Page", "terms", "is_published", 1)
			frappe.clear_cache()


class TestPersonalDataIsGuarded(FrappeTestCase):
	"""Signups and demo requests hold names, emails and phone numbers."""

	SENSITIVE = ("ip_address", "user_agent", "verification_token", "price_breakdown")

	def test_sensitive_fields_sit_at_permlevel_one(self):
		for doctype, fields in (
			("Subscription Signup", self.SENSITIVE),
			("Demo Request", ("ip_address", "user_agent")),
		):
			meta = frappe.get_meta(doctype)
			for fieldname in fields:
				field = meta.get_field(fieldname)
				if not field:
					continue
				self.assertEqual(
					field.permlevel, 1, f"{doctype}.{fieldname} is readable by anyone with access"
				)

	def test_the_verification_token_is_hidden_and_never_exported(self):
		field = frappe.get_meta("Subscription Signup").get_field("verification_token")
		self.assertTrue(field.hidden, "the verification token is visible on the form")
		self.assertTrue(field.no_copy, "the verification token would be copied on amend")
		self.assertEqual(field.permlevel, 1)

	def test_the_token_is_not_in_any_list_view_or_standard_filter(self):
		meta = frappe.get_meta("Subscription Signup")
		field = meta.get_field("verification_token")
		self.assertFalse(field.in_list_view)
		self.assertFalse(field.in_standard_filter)
		self.assertNotIn("verification_token", (meta.search_fields or ""))

	def test_only_platform_admin_holds_level_one(self):
		for doctype in ("Subscription Signup", "Demo Request"):
			granted = {
				row.role for row in frappe.get_meta(doctype).permissions if row.permlevel == 1
			}
			self.assertTrue(granted, f"{doctype} guards fields nobody can read")
			self.assertEqual(
				granted - {"Platform Admin", "System Manager"},
				set(),
				f"{doctype} grants personal data beyond Platform Admin",
			)

	def test_platform_sales_cannot_see_the_token_or_the_ip(self):
		for doctype in ("Subscription Signup", "Demo Request"):
			level_one = {
				row.role for row in frappe.get_meta(doctype).permissions if row.permlevel == 1
			}
			self.assertNotIn("Platform Sales", level_one)
