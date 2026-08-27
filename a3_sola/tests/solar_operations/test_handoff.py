# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sales Order to Solar Installation - the direct call that replaced the Phase 1 stub."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey
from a3_sola.tests.test_quotation import ensure_customer, ensure_item, make_quotation


class TestSalesOrderHandoff(FrappeTestCase):
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
		self.quotation = make_quotation(self.consumer, self.estimate, self.check)
		self.quotation.submit()

	def make_sales_order(self):
		order = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": self.consumer.company,
				"customer": ensure_customer(),
				"transaction_date": today(),
				"delivery_date": frappe.utils.add_days(today(), 30),
				"items": [
					{
						"item_code": ensure_item(),
						"qty": 1,
						"rate": 215000,
						"delivery_date": frappe.utils.add_days(today(), 30),
						"prevdoc_docname": self.quotation.name,
					}
				],
			}
		)
		order.flags.ignore_permissions = True
		order.insert(ignore_permissions=True)
		return order

	def test_submit_creates_the_installation(self):
		order = self.make_sales_order()
		order.submit()

		installation = frappe.db.get_value("Solar Installation", {"sales_order": order.name}, "name")
		self.assertTrue(installation, "no installation created from the sales order")

		doc = frappe.get_doc("Solar Installation", installation)
		self.assertEqual(doc.solar_consumer, self.consumer.name)
		self.assertEqual(doc.solar_design_estimate, self.estimate.name)
		self.assertEqual(doc.capacity_kw, self.estimate.final_capacity_kw)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(len(doc.stages), 19)

	def test_creation_is_idempotent(self):
		"""Re-running the handoff must not open a second job."""
		from a3_sola.api import handoff

		order = self.make_sales_order()
		order.submit()
		first = frappe.db.get_value("Solar Installation", {"sales_order": order.name}, "name")

		again = handoff.create_solar_installation(order)
		self.assertEqual(again, first)
		self.assertEqual(frappe.db.count("Solar Installation", {"sales_order": order.name}), 1)

	def test_consumer_advances_to_converted(self):
		order = self.make_sales_order()
		order.submit()
		self.assertEqual(
			frappe.db.get_value("Solar Consumer", self.consumer.name, "status"), "Converted"
		)

	def test_statutory_block_carried_across(self):
		order = self.make_sales_order()
		order.submit()
		doc = frappe.get_doc("Solar Installation", {"sales_order": order.name})
		self.assertEqual(doc.kseb_registration_fee, 3540)
		self.assertEqual(doc.kseb_registration_refundable, 2400)

	def test_sales_order_links_back(self):
		order = self.make_sales_order()
		order.submit()
		installation = frappe.db.get_value("Solar Installation", {"sales_order": order.name}, "name")
		self.assertEqual(
			frappe.db.get_value("Sales Order", order.name, "solar_installation"), installation
		)

	def test_non_solar_order_creates_nothing(self):
		order = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": self.consumer.company,
				"customer": ensure_customer(),
				"transaction_date": today(),
				"delivery_date": frappe.utils.add_days(today(), 30),
				"items": [
					{
						"item_code": ensure_item(),
						"qty": 1,
						"rate": 1000,
						"delivery_date": frappe.utils.add_days(today(), 30),
					}
				],
			}
		)
		order.flags.ignore_permissions = True
		order.insert(ignore_permissions=True)
		order.submit()
		self.assertFalse(frappe.db.exists("Solar Installation", {"sales_order": order.name}))
