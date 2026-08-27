# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Pricing arithmetic.

`calculate_plan_total` is the single source of truth for what anything costs, and Phase 5
charges from a snapshot of its output. If it is wrong, customers are charged the wrong
amount - so it is tested harder than anything else in this module.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import platform


class TestPlanPricing(FrappeTestCase):
	def test_monthly_with_no_add_ons(self):
		result = platform.calculate_plan_total("starter", "monthly")
		self.assertEqual(flt(result["base_amount"], 2), 3000.00)
		self.assertEqual(flt(result["additional_user_amount"], 2), 0.00)
		# Implementation is charged on monthly - that is the whole point of the annual offer.
		self.assertEqual(flt(result["implementation_fee"], 2), 10000.00)
		self.assertFalse(result["implementation_fee_waived"])
		self.assertEqual(flt(result["total_amount"], 2), 13000.00)

	def test_annual_waives_the_implementation_fee(self):
		result = platform.calculate_plan_total("starter", "annual")
		self.assertEqual(flt(result["base_amount"], 2), 30000.00)
		self.assertEqual(flt(result["implementation_fee"], 2), 0.00)
		self.assertTrue(result["implementation_fee_waived"])
		self.assertEqual(flt(result["total_amount"], 2), 30000.00)

	def test_the_waived_fee_is_still_shown_struck_through(self):
		"""A discount nobody sees is not a discount."""
		result = platform.calculate_plan_total("starter", "annual")
		fee_line = next(l for l in result["line_items"] if l.get("waived"))
		self.assertEqual(flt(fee_line["struck_amount"], 2), 10000.00)
		self.assertEqual(flt(fee_line["amount"], 2), 0.00)

	def test_monthly_with_three_additional_users_on_starter(self):
		result = platform.calculate_plan_total("starter", "monthly", additional_users=3)
		self.assertEqual(flt(result["additional_user_rate"], 2), 300.00)
		self.assertEqual(flt(result["additional_user_amount"], 2), 900.00)
		self.assertEqual(flt(result["total_amount"], 2), 13900.00)
		self.assertEqual(result["total_users"], 8)

	def test_annual_uses_the_annual_per_user_rate(self):
		"""Not the monthly rate multiplied by twelve - the plan states its own."""
		result = platform.calculate_plan_total("starter", "annual", additional_users=3)
		self.assertEqual(flt(result["additional_user_rate"], 2), 3000.00)
		self.assertEqual(flt(result["additional_user_amount"], 2), 9000.00)
		self.assertEqual(flt(result["total_amount"], 2), 39000.00)

	def test_growth_charges_less_per_additional_user_than_starter(self):
		starter = platform.calculate_plan_total("starter", "monthly", additional_users=1)
		growth = platform.calculate_plan_total("growth", "monthly", additional_users=1)
		self.assertLess(growth["additional_user_rate"], starter["additional_user_rate"])

	def test_a_custom_plan_returns_contact_sales_not_a_number(self):
		result = platform.calculate_plan_total("enterprise", "monthly")
		self.assertTrue(result["is_custom_pricing"])
		self.assertTrue(result["contact_sales"])
		self.assertEqual(result["line_items"], [])
		self.assertIn("agreed with our team", result["message"])

	def test_additional_users_beyond_the_plan_limit_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			platform.calculate_plan_total("starter", "monthly", additional_users=100)

	def test_an_unknown_plan_is_refused_not_defaulted(self):
		with self.assertRaises(frappe.ValidationError):
			platform.calculate_plan_total("does-not-exist", "monthly")

	def test_an_unknown_cycle_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			platform.calculate_plan_total("starter", "fortnightly")

	def test_negative_additional_users_are_floored_at_zero(self):
		result = platform.calculate_plan_total("starter", "monthly", additional_users=-5)
		self.assertEqual(result["additional_users"], 0)
		self.assertEqual(flt(result["additional_user_amount"], 2), 0.00)

	def test_the_calculation_is_pure(self):
		"""Same arguments, same answer, and nothing written anywhere."""
		before = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "modified")
		first = platform.calculate_plan_total("starter", "annual", additional_users=2)
		second = platform.calculate_plan_total("starter", "annual", additional_users=2)
		self.assertEqual(first, second)
		after = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "modified")
		self.assertEqual(before, after)

	def test_line_items_reconcile_to_the_total(self):
		for cycle in ("monthly", "annual"):
			for users in (0, 4):
				result = platform.calculate_plan_total("growth", cycle, additional_users=users)
				summed = sum(flt(line["amount"]) for line in result["line_items"])
				self.assertEqual(
					flt(summed, 2),
					flt(result["subtotal"], 2),
					f"{cycle} with {users} extra users does not add up",
				)


class TestPublishedPlans(FrappeTestCase):
	def test_plans_come_back_in_display_order(self):
		codes = [p["plan_code"] for p in platform.get_published_plans()]
		self.assertEqual(codes, ["starter", "growth", "enterprise"])

	def test_annual_saving_is_computed_for_the_card(self):
		starter = next(p for p in platform.get_published_plans() if p["plan_code"] == "starter")
		# 3000 x 12 = 36000 against an annual price of 30000.
		self.assertEqual(flt(starter["annual_equivalent"], 2), 36000.00)
		self.assertEqual(flt(starter["annual_saving"], 2), 6000.00)
		self.assertEqual(flt(starter["annual_effective_monthly"], 2), 2500.00)

	def test_the_popular_plan_is_marked(self):
		popular = [p["plan_code"] for p in platform.get_published_plans() if p["is_popular"]]
		self.assertEqual(popular, ["growth"])

	def test_each_plan_carries_its_features_and_modules(self):
		for plan in platform.get_published_plans():
			self.assertTrue(plan["features"], f"{plan['plan_code']} has no feature list")
			self.assertTrue(plan["modules"], f"{plan['plan_code']} enables no modules")

	def test_starter_does_not_include_the_projects_module(self):
		"""The tier boundary a prospect must not have to guess at."""
		starter = next(p for p in platform.get_published_plans() if p["plan_code"] == "starter")
		self.assertIn("Solar Operations", starter["modules"])
		self.assertNotIn("Solar Projects", starter["modules"])

	def test_growth_includes_all_three_modules(self):
		growth = next(p for p in platform.get_published_plans() if p["plan_code"] == "growth")
		self.assertEqual(
			set(growth["modules"]), {"Solar CRM", "Solar Operations", "Solar Projects"}
		)

	def test_growth_inherits_from_starter(self):
		growth = next(p for p in platform.get_published_plans() if p["plan_code"] == "growth")
		self.assertEqual(growth["inherits_from_name"], "Starter")

	def test_an_unpublished_plan_disappears_from_the_site(self):
		name = frappe.db.get_value("Subscription Plan", {"plan_code": "growth"}, "name")
		frappe.db.set_value("Subscription Plan", name, "is_published", 0)
		frappe.clear_cache(doctype="Subscription Plan")
		try:
			codes = [p["plan_code"] for p in platform.get_published_plans()]
			self.assertNotIn("growth", codes)
		finally:
			frappe.db.set_value("Subscription Plan", name, "is_published", 1)


class TestPlanValidation(FrappeTestCase):
	def _plan(self, **kwargs):
		values = {
			"doctype": "Subscription Plan",
			"plan_name": "Test Plan",
			"plan_code": "test-plan",
			"monthly_price": 1000,
			"included_users": 3,
			"currency": "INR",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		return doc

	def test_an_uppercase_plan_code_is_normalised(self):
		doc = self._plan(plan_code="Test-Plan")
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.plan_code, "test-plan")

	def test_a_plan_code_with_spaces_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._plan(plan_code="test plan").insert(ignore_permissions=True)

	def test_a_self_serve_plan_needs_a_price(self):
		with self.assertRaises(frappe.ValidationError):
			self._plan(monthly_price=0).insert(ignore_permissions=True)

	def test_a_self_serve_plan_needs_included_users(self):
		with self.assertRaises(frappe.ValidationError):
			self._plan(included_users=0).insert(ignore_permissions=True)

	def test_a_custom_plan_needs_neither(self):
		doc = self._plan(
			plan_code="custom-tier", monthly_price=0, included_users=0, is_custom_pricing=1
		)
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)

	def test_a_maximum_below_the_included_count_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._plan(included_users=10, max_users=5).insert(ignore_permissions=True)

	def test_a_plan_cannot_inherit_from_itself(self):
		doc = self._plan(plan_code="loop-plan")
		doc.insert(ignore_permissions=True)
		doc.inherits_from_plan = doc.name
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
