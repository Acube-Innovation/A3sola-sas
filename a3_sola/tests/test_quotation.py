# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Quotation: the subsidy rule and the submission gates."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.tests.fixtures import default_company, make_consumer, make_estimate, make_survey


def ensure_item(code="Solar Package Test Item"):
	if frappe.db.exists("Item", code):
		return code
	if not frappe.db.exists("Item Group", "Solar Packages"):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": "Solar Packages",
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": "Solar Packages",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
		}
	).insert(ignore_permissions=True)
	return code


def ensure_customer(name="Solar Test Customer"):
	if frappe.db.exists("Customer", name):
		return name
	frappe.get_doc(
		{"doctype": "Customer", "customer_name": name, "customer_type": "Individual"}
	).insert(ignore_permissions=True)
	return name


def make_quotation(consumer, estimate, check=None, items=None, **kwargs):
	values = {
		"doctype": "Quotation",
		"company": consumer.company,
		"quotation_to": "Customer",
		"party_name": ensure_customer(),
		"solar_consumer": consumer.name,
		"solar_design_estimate": estimate.name,
		"subsidy_eligibility_check": check.name if check else None,
		"items": items
		or [{"item_code": ensure_item(), "qty": 1, "rate": 215000, "description": "3 kWp rooftop solar plant"}],
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


class TestQuotationSolarLayer(FrappeTestCase):
	def setUp(self):
		self.consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		self.survey = make_survey(self.consumer, segments=((240, True),))
		self.estimate = make_estimate(self.consumer, self.survey, submit=True)
		self.check = frappe.get_doc(
			{
				"doctype": "Subsidy Eligibility Check",
				"company": self.consumer.company,
				"solar_consumer": self.consumer.name,
				"design_estimate": self.estimate.name,
				"subsidy_scheme": self.estimate.subsidy_scheme,
			}
		).insert(ignore_permissions=True)

	def test_solar_figures_are_fetched_not_typed(self):
		quotation = make_quotation(self.consumer, self.estimate, self.check)
		self.assertEqual(quotation.capacity_kw, self.estimate.final_capacity_kw)
		self.assertEqual(quotation.expected_subsidy_to_customer, 78000)
		self.assertEqual(quotation.kseb_registration_fee, 3540)
		self.assertEqual(quotation.kseb_registration_refundable, 2400)

	def test_subsidy_never_affects_the_quotation_total(self):
		"""The subsidy is a government transfer to the customer, not a discount."""
		quotation = make_quotation(self.consumer, self.estimate, self.check)
		self.assertEqual(quotation.grand_total, 215000)
		self.assertGreater(quotation.expected_subsidy_to_customer, 0)

	def test_statutory_fees_are_absent_from_items_and_taxes(self):
		quotation = make_quotation(self.consumer, self.estimate, self.check)
		self.assertEqual(quotation.total, 215000)
		descriptions = " ".join((row.description or "") for row in quotation.items).lower()
		self.assertNotIn("registration fee", descriptions)

	def test_a_subsidy_item_row_is_rejected(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_quotation(
				self.consumer,
				self.estimate,
				self.check,
				items=[
					{"item_code": ensure_item(), "qty": 1, "rate": 215000, "description": "3 kWp plant"},
					{"item_code": ensure_item(), "qty": 1, "rate": -78000, "description": "Less: Government subsidy"},
				],
			)
		self.assertIn("subsidy", str(ctx.exception).lower())

	def test_submission_blocked_without_an_eligibility_check(self):
		quotation = make_quotation(self.consumer, self.estimate, check=None)
		with self.assertRaises(frappe.ValidationError) as ctx:
			quotation.submit()
		self.assertIn("Eligibility Check", str(ctx.exception))

	def test_submission_blocked_when_not_eligible(self):
		consumer = make_consumer(
			avg_consumption_units=750, sanctioned_load_kw=5, has_availed_prior_subsidy=1
		)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey, submit=True)
		check = frappe.get_doc(
			{
				"doctype": "Subsidy Eligibility Check",
				"company": consumer.company,
				"solar_consumer": consumer.name,
				"design_estimate": estimate.name,
				"subsidy_scheme": estimate.subsidy_scheme,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(check.overall_result, "Not Eligible")

		quotation = make_quotation(consumer, estimate, check)
		with self.assertRaises(frappe.ValidationError) as ctx:
			quotation.submit()
		self.assertIn("Not Eligible", str(ctx.exception))

	def test_submit_advances_consumer_to_quoted(self):
		quotation = make_quotation(self.consumer, self.estimate, self.check)
		quotation.submit()
		self.assertEqual(frappe.db.get_value("Solar Consumer", self.consumer.name, "status"), "Quoted")

	def test_option_must_be_chosen_when_several_are_quoted(self):
		consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(
			consumer,
			survey,
			submit=True,
			options=[
				{"option_name": "Option 1", "inverter_topology": "String", "system_cost": 215000, "is_recommended": 1},
				{"option_name": "Option 2", "inverter_topology": "String with Optimiser", "system_cost": 225000},
			],
		)
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_quotation(consumer, estimate)
		self.assertIn("options", str(ctx.exception).lower())
