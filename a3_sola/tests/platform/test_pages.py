# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The public site, rendered as a guest actually sees it.

Every assertion here is about data reaching the page. If a marketer unpublishes something
in the desk it has to leave the site, and if they change a price the site has to change -
that is the whole reason none of this is written in a template.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response

from a3_sola.api.platform import base_route
from a3_sola.api.platform import route as public_route


def render(path):
	"""Render as a logged-out visitor, the way the public sees it.

	Takes a path relative to the public site's base, so these tests keep working wherever
	the site is mounted. `render("pricing")` and `render("/pricing")` both mean the pricing
	page, not a page at the server root.
	"""
	# Idempotent. Some callers pass a path relative to the site ("pricing"); others pass a
	# route read straight off a record, which already carries the base
	# ("a3sola/features/..."). Prefixing the second kind again gives /a3sola/a3sola/... and
	# a 404 that looks like a routing bug rather than a test bug.
	relative = path.lstrip("/")
	prefix = base_route()
	if prefix and (relative == prefix or relative.startswith(prefix + "/")):
		full = "/" + relative
	else:
		full = public_route(relative)
	frappe.set_user("Guest")
	set_request(method="GET", path=full)
	response = get_response(full)
	return response.status_code, response.get_data(as_text=True)


class TestHomepage(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_homepage_is_public(self):
		status, html = render("")
		self.assertEqual(status, 200)
		self.assertIn("a3s-hero", html)

	def test_every_section_is_present(self):
		_status, html = render("")
		for anchor in (
			'id="features"', 'id="solutions"', 'id="subsidy"', 'id="platform"',
			'id="integrations"', 'id="pricing"', 'id="apps"', 'id="contact"',
		):
			self.assertIn(anchor, html, f"missing section {anchor}")

	def test_every_published_plan_appears_with_its_price(self):
		_status, html = render("")
		for plan in frappe.get_all(
			"Subscription Plan",
			filters={"is_published": 1, "is_active": 1},
			fields=["plan_name", "monthly_price", "is_custom_pricing", "currency"],
		):
			self.assertIn(plan.plan_name, html)
			if not plan.is_custom_pricing:
				self.assertIn(
					frappe.utils.fmt_money(plan.monthly_price, currency=plan.currency),
					html,
					f"{plan.plan_name}'s price is not on the page",
				)

	def test_a_custom_plan_shows_custom_not_a_number(self):
		_status, html = render("")
		self.assertIn("Custom", html)

	def test_every_published_feature_appears(self):
		import html as html_lib

		_status, page = render("")
		# Compare unescaped, so an ampersand in a feature name is not a false failure.
		unescaped = html_lib.unescape(page)
		for name in frappe.get_all(
			"Platform Feature",
			filters={"is_published": 1, "show_on_homepage": 1},
			pluck="feature_name",
		):
			self.assertIn(name, unescaped, f"{name} is missing from the homepage")

	def test_unpublishing_a_feature_removes_it_from_the_homepage(self):
		name = frappe.db.get_value("Platform Feature", {"is_published": 1}, "name")
		title = frappe.db.get_value("Platform Feature", name, "feature_name")
		route = frappe.db.get_value("Platform Feature", name, "route")
		frappe.db.set_value("Platform Feature", name, "is_published", 0)
		frappe.clear_cache()
		try:
			_status, html = render("")
			self.assertNotIn(f'href="/{route}"', html)
		finally:
			frappe.db.set_value("Platform Feature", name, "is_published", 1)
			frappe.clear_cache()

	def test_every_stat_appears(self):
		_status, html = render("")
		for stat in frappe.get_all(
			"Platform Stat", filters={"is_published": 1}, fields=["stat_value", "stat_label"]
		):
			self.assertIn(stat.stat_label, html)

	def test_integrations_without_a_logo_fall_back_to_an_initial(self):
		_status, html = render("")
		self.assertIn("a3s-chip__initial", html)

	def test_organization_schema_is_emitted(self):
		_status, html = render("")
		self.assertIn('"@type": "Organization"', html)

	def test_nothing_links_to_an_external_cdn_for_behaviour(self):
		"""One font stylesheet is allowed; scripts must all be ours."""
		import re

		_status, html = render("")
		for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
			self.assertFalse(
				src.startswith("http") and "localhost" not in src,
				f"external script on the homepage: {src}",
			)


class TestPricingLinks(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_every_pricing_cta_carries_package_and_cycle(self):
		"""Phase 5 reads both parameters. A CTA that drops one breaks the funnel."""
		import re

		_status, html = render("")
		links = re.findall(rf'href="({re.escape(public_route("get-started"))}\?[^"]*)"', html)
		self.assertTrue(links, "no pricing CTA links found")
		for link in links:
			self.assertIn("package=", link)
			self.assertIn("cycle=", link)

	def test_every_self_serve_plan_has_a_cta(self):
		import re

		_status, html = render("")
		codes = set(re.findall(r'package=([a-z0-9-]+)', html))
		for plan_code in frappe.get_all(
			"Subscription Plan",
			filters={"is_published": 1, "is_active": 1, "is_custom_pricing": 0},
			pluck="plan_code",
		):
			self.assertIn(plan_code, codes, f"{plan_code} has no pricing CTA")

	def test_the_custom_plan_goes_to_sales_not_to_signup(self):
		import re

		_status, html = render("")
		codes = set(re.findall(r'package=([a-z0-9-]+)', html))
		for plan_code in frappe.get_all(
			"Subscription Plan", filters={"is_custom_pricing": 1}, pluck="plan_code"
		):
			self.assertNotIn(plan_code, codes, f"{plan_code} is custom but offers self-serve signup")


class TestContentPages(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_features_index_renders(self):
		status, html = render("/features")
		self.assertEqual(status, 200)
		self.assertIn("Features", html)

	def test_the_solutions_index_renders(self):
		status, html = render("/solutions")
		self.assertEqual(status, 200)

	def test_every_feature_detail_route_resolves(self):
		for route in frappe.get_all("Platform Feature", filters={"is_published": 1}, pluck="route"):
			status, _html = render("/" + route)
			self.assertEqual(status, 200, f"/{route} did not resolve")

	def test_every_solution_detail_route_resolves(self):
		for route in frappe.get_all("Platform Solution", filters={"is_published": 1}, pluck="route"):
			status, _html = render("/" + route)
			self.assertEqual(status, 200, f"/{route} did not resolve")

	def test_an_unpublished_feature_is_not_reachable(self):
		name = frappe.db.get_value("Platform Feature", {"is_published": 1}, "name")
		route = frappe.db.get_value("Platform Feature", name, "route")
		frappe.db.set_value("Platform Feature", name, "is_published", 0)
		frappe.clear_cache()
		try:
			status, _html = render("/" + route)
			self.assertEqual(status, 404, "an unpublished feature is still public")
		finally:
			frappe.db.set_value("Platform Feature", name, "is_published", 1)
			frappe.clear_cache()

	def test_a_detail_page_emits_breadcrumb_schema(self):
		route = frappe.db.get_value("Platform Feature", {"is_published": 1}, "route")
		_status, html = render("/" + route)
		self.assertIn('"@type": "BreadcrumbList"', html)


class TestPricingPage(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_pricing_page_renders(self):
		status, html = render("/pricing")
		self.assertEqual(status, 200)
		self.assertIn("a3s-table", html)

	def test_the_comparison_table_carries_the_additional_user_rates(self):
		_status, html = render("/pricing")
		for plan in frappe.get_all(
			"Subscription Plan",
			filters={"is_published": 1, "is_custom_pricing": 0},
			fields=["additional_user_price_monthly", "additional_user_price_annual", "currency"],
		):
			self.assertIn(
				frappe.utils.fmt_money(plan.additional_user_price_monthly, currency=plan.currency),
				html,
			)
			self.assertIn(
				frappe.utils.fmt_money(plan.additional_user_price_annual, currency=plan.currency),
				html,
			)

	def test_the_faq_renders_with_its_schema(self):
		_status, html = render("/pricing")
		self.assertIn('"@type": "FAQPage"', html)
		for question in frappe.get_all("Platform FAQ", filters={"is_published": 1}, pluck="question"):
			self.assertIn(frappe.utils.escape_html(question), html)

	def test_software_schema_lists_the_offers(self):
		_status, html = render("/pricing")
		self.assertIn('"@type": "SoftwareApplication"', html)

	def test_a_price_change_reaches_the_site_immediately(self):
		"""The point of the content model: no deploy to change a price."""
		name = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		original = frappe.db.get_value("Subscription Plan", name, "monthly_price")
		frappe.db.set_value("Subscription Plan", name, "monthly_price", 4321)
		frappe.clear_cache()
		try:
			_status, html = render("/pricing")
			self.assertIn(frappe.utils.fmt_money(4321, currency="INR"), html)
		finally:
			frappe.db.set_value("Subscription Plan", name, "monthly_price", original)
			frappe.clear_cache()


class TestLegalPages(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_all_three_legal_pages_render(self):
		for route in ("/legal/privacy", "/legal/terms", "/legal/refund-policy"):
			status, _html = render(route)
			self.assertEqual(status, 200, f"{route} did not render")

	def test_unreviewed_legal_text_carries_a_draft_banner(self):
		"""Unreviewed legal text must never look final."""
		for route in ("/legal/privacy", "/legal/terms", "/legal/refund-policy"):
			_status, html = render(route)
			self.assertIn("a3s-draft", html, f"{route} presents unreviewed text as final")
			self.assertIn("has not yet been reviewed by a lawyer", html)

	def test_the_banner_goes_when_the_review_is_recorded(self):
		frappe.db.set_value(
			"Platform Legal Page",
			"privacy",
			{
				"reviewed_by_lawyer": 1,
				"reviewed_by": "Test Counsel",
				"reviewed_on": frappe.utils.today(),
			},
		)
		frappe.clear_cache()
		try:
			_status, html = render("/legal/privacy")
			self.assertNotIn("a3s-draft", html)
			self.assertIn("Test Counsel", html)
		finally:
			frappe.db.set_value("Platform Legal Page", "privacy", "reviewed_by_lawyer", 0)
			frappe.clear_cache()

	def test_a_review_cannot_be_claimed_without_saying_who(self):
		doc = frappe.get_doc("Platform Legal Page", "terms")
		doc.reviewed_by_lawyer = 1
		doc.reviewed_by = None
		doc.reviewed_on = None
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestMaintenanceMode(FrappeTestCase):
	def tearDown(self):
		frappe.db.set_single_value("A3 Sola Settings", "maintenance_mode", 0)
		frappe.clear_cache()
		frappe.set_user("Administrator")

	def test_maintenance_intercepts_the_homepage(self):
		frappe.db.set_single_value("A3 Sola Settings", "maintenance_mode", 1)
		frappe.clear_cache()
		_status, html = render("")
		self.assertIn("a3s-maintenance", html)
		self.assertNotIn("a3s-hero", html)

	def test_maintenance_intercepts_the_pricing_page_too(self):
		frappe.db.set_single_value("A3 Sola Settings", "maintenance_mode", 1)
		frappe.clear_cache()
		_status, html = render("/pricing")
		self.assertIn("a3s-maintenance", html)

	def test_legal_pages_stay_up_during_maintenance(self):
		"""Somebody may be relying on the privacy policy. A banner is not a substitute."""
		frappe.db.set_single_value("A3 Sola Settings", "maintenance_mode", 1)
		frappe.clear_cache()
		status, html = render("/legal/privacy")
		self.assertEqual(status, 200)
		self.assertNotIn("a3s-maintenance", html)
		self.assertIn("a3s-legal", html)
