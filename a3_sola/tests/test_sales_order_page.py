# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The sales order page: a lead, then one of its quotations - required - ordered as quoted
with the dates the order asks for (api/sales_order_option)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import sales_order_option as so
from a3_sola.overrides.sales_order import default_delivery_date
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey
from a3_sola.tests.test_quotation import make_quotation


class TestSalesOrderPage(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		self.lead = self.consumer.lead
		estimate = make_estimate(self.consumer, make_survey(self.consumer))
		self.first = make_quotation(self.consumer, estimate)
		self.first.submit()
		self.second = make_quotation(self.consumer, estimate)
		self.second.submit()
		self.draft = make_quotation(self.consumer, estimate)
		self.when = {"delivery_date": default_delivery_date()}

	def cards(self, order=None):
		return {c["quotation"]: c for c in so.quotations(lead=self.lead, order=order)}

	def test_the_lead_lists_its_quotations_and_says_which_can_be_ordered(self):
		cards = self.cards()
		self.assertTrue({self.first.name, self.second.name, self.draft.name} <= set(cards))
		self.assertTrue(cards[self.first.name]["orderable"])
		self.assertFalse(cards[self.draft.name]["orderable"])
		self.assertIn("submit it first", cards[self.draft.name]["reason"])
		self.assertIn(self.lead, [c["value"] for c in so.lead_choices()])

	def test_a_quotation_must_be_chosen(self):
		with self.assertRaises(frappe.MandatoryError):
			so.save_order(None, self.when)

	def test_the_order_is_the_quotation_with_the_dates_asked(self):
		order = frappe.get_doc("Sales Order", so.save_order(self.first.name, self.when)["name"])
		self.assertEqual(so.current_quotation(order), self.first.name)
		self.assertEqual(order.customer, self.first.party_name)
		self.assertEqual(flt(order.grand_total), flt(self.first.grand_total))
		self.assertEqual(str(order.delivery_date), self.when["delivery_date"])
		self.assertTrue(all(str(r.delivery_date) == self.when["delivery_date"] for r in order.items))

	def test_a_quotation_is_ordered_once(self):
		name = so.save_order(self.first.name, self.when)["name"]
		self.assertFalse(self.cards()[self.first.name]["orderable"])
		self.assertIn(name, self.cards()[self.first.name]["reason"])
		with self.assertRaises(frappe.ValidationError):
			so.save_order(self.first.name, self.when)
		# The order's own quotation is still its to keep.
		self.assertTrue(self.cards(order=name)[self.first.name]["orderable"])
		so.save_order(self.first.name, {"delivery_date": self.when["delivery_date"]}, name=name)

	def test_a_draft_quotation_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			so.save_order(self.draft.name, self.when)

	def test_a_draft_order_can_be_pointed_at_another_quotation(self):
		name = so.save_order(self.first.name, self.when)["name"]
		self.assertEqual(so.save_order(self.second.name, self.when, name=name)["name"], name)
		order = frappe.get_doc("Sales Order", name)
		self.assertEqual(so.current_quotation(order), self.second.name)
		self.assertEqual(len(order.items), len(self.second.items))
		self.assertTrue(self.cards()[self.first.name]["orderable"], "the first quotation is free again")

	def test_a_delivery_date_is_required(self):
		with self.assertRaises(frappe.MandatoryError):
			so.save_order(self.first.name, {"delivery_date": ""})

	def test_the_tabs_show_the_quotation(self):
		view = so.quotation_view(self.first.name)
		self.assertEqual(set(view), {"details", "bom", "terms", "preview"})
		self.assertIn(self.first.name, view["details"])
		self.assertIn("Order Value", view["details"])
