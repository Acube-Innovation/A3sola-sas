# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The sales order page: a lead, then one of its quotations - required - ordered as quoted
with the dates the order asks for (api/sales_order_option)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import sales_order_option as so
from a3_sola.overrides.sales_order import default_delivery_date
from a3_sola.tests.fixtures import ensure_gst_fields, make_consumer, make_estimate, make_survey
from a3_sola.tests.test_quotation import make_quotation


class TestSalesOrderPage(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_gst_fields()
		self.consumer = make_consumer()
		self.lead = self.consumer.lead
		estimate = self.estimate = make_estimate(self.consumer, make_survey(self.consumer))
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

	def test_the_page_shows_the_proposal_the_order_is_made_under(self):
		from a3_sola.tests.test_proposal import make_proposal

		self.assertIsNone(so.proposal_of(lead=self.lead))
		proposal = make_proposal(self.estimate, self.consumer)
		shown = so.proposal_of(lead=self.lead)
		self.assertEqual(shown["name"], proposal.name)
		self.assertEqual(shown["route"], "/a3solaportal/proposals/" + proposal.name)
		# A quotation without a proposal of its own still shows the lead's.
		self.assertEqual(so.proposal_of(quotation=self.first.name, lead=self.lead)["name"], proposal.name)

	def test_the_customer_box_is_fetched_from_the_quotation(self):
		box = so.party_box(quotation=self.first.name)
		self.assertEqual(box["customer"], self.first.party_name)
		self.assertIn(self.first.party_name, [c["value"] for c in box["customers"]])
		self.assertIn("Unregistered", box["categories"])
		self.assertIn("32-Kerala", box["places"])
		self.assertEqual(box["from_lead"], "")

	def test_the_customer_details_chosen_are_kept_on_the_order_and_read_only_once_submitted(self):
		values = dict(self.when, contact_email="jacob@example.com", gst_category="Registered Regular",
			billing_address_gstin="32abcde1234f1z5", place_of_supply="32-Kerala")
		order = frappe.get_doc("Sales Order", so.save_order(self.first.name, values)["name"])
		self.assertEqual(order.contact_email, "jacob@example.com")
		self.assertEqual(order.gst_category, "Registered Regular")
		self.assertEqual(order.billing_address_gstin, "32ABCDE1234F1Z5")
		self.assertEqual(order.place_of_supply, "32-Kerala")
		# Kept on the customer too, where the order reads it from.
		self.assertEqual(frappe.db.get_value("Customer", order.customer, "gstin"), "32ABCDE1234F1Z5")
		# The box shows the order's own details once it exists.
		box = so.party_box(quotation=self.first.name, order=order.name)
		self.assertEqual((box["gstin"], box["email"]), ("32ABCDE1234F1Z5", "jacob@example.com"))
		order.submit()
		self.assertRaises(frappe.ValidationError, so.save_order, self.first.name, dict(values, contact_email="x@example.com"), order.name)
		frappe.db.set_value("Customer", order.customer, {"gstin": None, "gst_category": "Unregistered"})

	def test_a_registered_customer_needs_a_gstin(self):
		self.assertRaises(frappe.MandatoryError, so.save_order, self.first.name,
			dict(self.when, gst_category="Registered Regular", billing_address_gstin=""))
		self.assertRaises(frappe.ValidationError, so.save_order, self.first.name,
			dict(self.when, gst_category="Registered Regular", billing_address_gstin="not-a-gstin"))

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
