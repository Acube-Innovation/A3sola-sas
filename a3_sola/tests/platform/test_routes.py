# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every public page has a controller Frappe can actually import.

Frappe resolves a page controller as `<app>.www.<dirs>.<basename>`, converting hyphens in
the BASENAME only. So `verify-email.py` is never loaded (it looks for `verify_email.py`),
and a controller in a hyphenated DIRECTORY cannot be imported at all. Both failures are
silent: the template renders with no context and quietly shows its fallback branch.

This test is what stops that happening again.
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

import a3_sola

WWW = os.path.join(os.path.dirname(a3_sola.__file__), "www")

#: Every route the public site exposes, and what proves it rendered its own content.
PUBLIC_ROUTES = (
	("/", "a3s-hero"),
	("/features", "a3s-crumbs"),
	("/solutions", "a3s-crumbs"),
	("/pricing", "a3s-table"),
	("/get-started", "a3s-steps"),
	("/get-started/check-email", "Check your email"),
	("/get-started/summary", "a3s-narrow"),
	("/verify-email", "a3s-card__icon"),
	("/thank-you", "What happens next"),
	("/legal/privacy", "a3s-legal"),
	("/legal/terms", "a3s-legal"),
	("/legal/refund-policy", "a3s-legal"),
)


class TestPublicRoutes(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_every_public_route_renders_its_own_content(self):
		for route, marker in PUBLIC_ROUTES:
			with self.subTest(route=route):
				frappe.set_user("Guest")
				set_request(method="GET", path=route)
				response = get_response(route)
				self.assertEqual(response.status_code, 200, f"{route} did not return 200")
				self.assertIn(
					marker,
					response.get_data(as_text=True),
					f"{route} rendered without its own content",
				)

	def test_no_page_controller_is_unreachable(self):
		"""A .py beside a template must be named so Frappe can find it."""
		unreachable = []
		for root, _dirs, files in os.walk(WWW):
			relative = os.path.relpath(root, WWW)
			if "__pycache__" in root:
				continue
			# A hyphen anywhere in the directory path makes every controller under it
			# unimportable, because the module path is not a valid Python identifier.
			if relative != "." and "-" in relative:
				unreachable += [
					os.path.join(relative, f) for f in files if f.endswith(".py")
				]
			for filename in files:
				if not filename.endswith(".py") or filename == "__init__.py":
					continue
				if "-" in filename:
					unreachable.append(os.path.join(relative, filename))
		self.assertEqual(
			unreachable, [], f"these controllers can never be imported: {unreachable}"
		)

	def test_every_template_that_needs_context_has_a_controller(self):
		"""A template whose controller is missing renders its fallback branch silently."""
		missing = []
		for root, _dirs, files in os.walk(WWW):
			if "__pycache__" in root:
				continue
			for filename in files:
				if not filename.endswith(".html"):
					continue
				base = os.path.join(root, filename[:-5])
				controller = os.path.join(
					os.path.dirname(base), os.path.basename(base).replace("-", "_") + ".py"
				)
				if not os.path.exists(controller):
					missing.append(os.path.relpath(base, WWW))
		# Only the legal templates are allowed to be controller-free; they are not.
		self.assertEqual(missing, [], f"templates with no controller: {missing}")

	def test_the_signup_routes_are_not_indexable(self):
		"""A signup page in search results is a signup page being crawled."""
		for route in ("/get-started", "/verify-email", "/thank-you", "/get-started/summary"):
			frappe.set_user("Guest")
			set_request(method="GET", path=route)
			html = get_response(route).get_data(as_text=True)
			self.assertIn("noindex", html, f"{route} is indexable")

	def test_the_marketing_routes_are_indexable(self):
		for route in ("/", "/features", "/pricing"):
			frappe.set_user("Guest")
			set_request(method="GET", path=route)
			html = get_response(route).get_data(as_text=True)
			self.assertNotIn("noindex", html, f"{route} is blocked from search")
