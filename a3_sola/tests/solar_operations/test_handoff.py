# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sales Order to Solar Installation: the project is opened from the order's Next steps."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.setup import seed_stages
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey
from a3_sola.tests.test_quotation import ensure_customer, ensure_item, make_quotation
from a3_sola.overrides.sales_order import working_day


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
				"delivery_date": working_day(frappe.utils.add_days(today(), 30)),
				"items": [
					{
						"item_code": ensure_item(),
						"qty": 1,
						"rate": 215000,
						"delivery_date": working_day(frappe.utils.add_days(today(), 30)),
						"prevdoc_docname": self.quotation.name,
					}
				],
			}
		)
		order.flags.ignore_permissions = True
		order.insert(ignore_permissions=True)
		return order

	def open_project(self, order):
		"""Submit the order, then press Create project in its Next steps."""
		from a3_sola.api import portal_crud

		order.submit()
		return portal_crud.create_mapped(slug="projects", source_dt="Sales Order", source=order.name)

	def test_submit_alone_opens_no_project(self):
		order = self.make_sales_order()
		order.submit()
		self.assertFalse(frappe.db.exists("Solar Installation", {"sales_order": order.name}))

	def test_next_steps_offer_the_project_then_show_it(self):
		from a3_sola.api import portal_chain

		order = self.make_sales_order()
		step = portal_chain.steps_for(order)[0]
		self.assertEqual((step["key"], step["blocked"], step["done"]), ("project", True, False))

		made = self.open_project(order)
		step = portal_chain.steps_for(order)[0]
		self.assertTrue(step["done"])
		self.assertEqual((step["card"]["name"], step["card"]["doctype_label"]), (made["name"], "Project"))
		self.assertEqual(made["route"], "/a3solaportal/projects/" + made["name"])

	def test_create_project_opens_the_installation(self):
		order = self.make_sales_order()
		self.open_project(order)

		installation = frappe.db.get_value("Solar Installation", {"sales_order": order.name}, "name")
		self.assertTrue(installation, "no installation created from the sales order")

		doc = frappe.get_doc("Solar Installation", installation)
		self.assertEqual(doc.solar_consumer, self.consumer.name)
		self.assertEqual(doc.solar_design_estimate, self.estimate.name)
		self.assertEqual(doc.capacity_kw, self.estimate.final_capacity_kw)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(len(doc.stages), len(seed_stages.TASKS))

	def test_the_order_completes_the_first_task_and_is_its_document(self):
		order = self.make_sales_order()
		self.open_project(order)
		doc = frappe.get_doc("Solar Installation", {"sales_order": order.name})
		ord_row = next(r for r in doc.stages if r.stage_code == "ORD")
		self.assertEqual(ord_row.status, "Completed")
		self.assertEqual((ord_row.task_doctype, ord_row.task_document), ("Sales Order", order.name))
		self.assertEqual(str(ord_row.actual_completion_date), str(order.transaction_date))

	def test_creation_is_idempotent(self):
		"""Re-running the handoff must not open a second job."""
		from a3_sola.api import handoff

		order = self.make_sales_order()
		self.open_project(order)
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
		self.open_project(order)
		doc = frappe.get_doc("Solar Installation", {"sales_order": order.name})
		self.assertEqual(doc.kseb_registration_fee, 3540)
		self.assertEqual(doc.kseb_registration_refundable, 2400)

	def test_installation_links_to_the_order(self):
		"""The order is ERPNext's own form: the installation carries the link, not the order."""
		order = self.make_sales_order()
		self.open_project(order)
		installation = frappe.db.get_value("Solar Installation", {"sales_order": order.name}, "name")
		self.assertTrue(installation)
		self.assertFalse(frappe.get_meta("Sales Order").has_field("solar_installation"))

	def test_non_solar_order_creates_nothing(self):
		order = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": self.consumer.company,
				"customer": ensure_customer(),
				"transaction_date": today(),
				"delivery_date": working_day(frappe.utils.add_days(today(), 30)),
				"items": [
					{
						"item_code": ensure_item(),
						"qty": 1,
						"rate": 1000,
						"delivery_date": working_day(frappe.utils.add_days(today(), 30)),
					}
				],
			}
		)
		order.flags.ignore_permissions = True
		order.insert(ignore_permissions=True)
		order.submit()
		from a3_sola.api import portal_crud

		with self.assertRaises(frappe.ValidationError):
			portal_crud.create_mapped(slug="projects", source_dt="Sales Order", source=order.name)
		self.assertFalse(frappe.db.exists("Solar Installation", {"sales_order": order.name}))


class TestHandoffBilling(TestSalesOrderHandoff):
	def test_the_billing_plan_exists_from_the_order_with_the_advance_triggered(self):
		order = self.make_sales_order()
		self.open_project(order)
		installation = frappe.db.get_value("Solar Installation", {"sales_order": order.name}, "name")
		plan = frappe.db.get_value("Solar Billing Plan", {"solar_installation": installation, "docstatus": 1}, "name")
		self.assertTrue(plan, "no billing plan created at handoff")
		doc = frappe.get_doc("Solar Billing Plan", plan)
		advance = next(r for r in doc.milestones if r.trigger_type == "On Order")
		self.assertTrue(advance.is_triggered, "the advance did not trigger on the order")
