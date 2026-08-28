# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One intent to collect a specific amount.

Two things about this record are load-bearing:

**The amounts are a copy, not a calculation.** They come from the source's pricing
snapshot. Nothing here calls `calculate_plan_total` - the applicant agreed to a number and
this is that number, even if marketing changed the plan an hour later.

**`amount_in_paise` is computed once, here.** Razorpay works in the smallest currency
unit, and `int(35400.00 * 100)` can come out one paisa short because 354.00 has no exact
binary form. It is converted through Decimal once and never re-derived downstream.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api import tax
from a3_sola.api.naming import set_name

#: Statuses a person may never set by hand. Payment state comes from the gateway.
TERMINAL = ("Paid", "Refunded", "Cancelled", "Expired")


class PaymentOrder(Document):
	def autoname(self):
		set_name(self, "payment_order_series_prefix", ".YYYY.-.#####", fallback="PORD")

	def validate(self):
		self.resolve_tax()
		self.compute_amount_in_paise()
		self.assert_amounts_reconcile()

	def resolve_tax(self):
		"""Derive the split from where the customer actually is."""
		self.customer_gstin = tax.validate_gstin(self.customer_gstin, self.customer_state_code)
		if self.customer_gstin and not self.customer_state_code:
			self.customer_state_code = self.customer_gstin[:2]

		code, place = tax.resolve_place_of_supply(
			self.place_of_supply, self.customer_state_code, self.customer_gstin
		)
		self.customer_state_code = code or self.customer_state_code
		self.place_of_supply = self.place_of_supply or place

		split = tax.compute_tax(self.subtotal, self.customer_state_code)
		self.tax_type = split["tax_type"]
		self.igst_amount = split["igst_amount"]
		self.cgst_amount = split["cgst_amount"]
		self.sgst_amount = split["sgst_amount"]

	def compute_amount_in_paise(self):
		self.amount_in_paise = tax.to_paise(self.total_amount)

	def assert_amounts_reconcile(self):
		"""Subtotal plus tax must equal the total, to the paisa.

		If these ever disagree the customer is charged one number and invoiced another,
		and nobody notices until a reconciliation months later.
		"""
		expected = flt(flt(self.subtotal) + flt(self.tax_amount), 2)
		if abs(expected - flt(self.total_amount, 2)) > 0.01:
			frappe.throw(
				_("Subtotal {0} plus tax {1} is {2}, but the total says {3}.").format(
					self.subtotal, self.tax_amount, expected, self.total_amount
				),
				title=_("Amounts Do Not Add Up"),
			)
		if tax.to_paise(self.total_amount) != cint(self.amount_in_paise):
			frappe.throw(_("The gateway amount does not match the total."))

	def before_submit(self):
		if not self.gateway_order_id and self.collection_mode == "Checkout":
			frappe.throw(
				_("This order has no gateway order id, so nothing can be collected against it."),
				title=_("Not Ready to Submit"),
			)

	def set_status(self, status, reason=None, error_code=None, error_description=None):
		"""The only way status moves. Never settable from the web."""
		if self.status == status:
			return False
		self.status = status
		if error_code:
			self.last_error_code = error_code
		if error_description:
			self.last_error_description = error_description
		frappe.logger("a3_sola").info(
			{
				"event": "payment_order_status",
				"order": self.name,
				"status": status,
				"reason": reason,
			}
		)
		return True

	def on_cancel(self):
		if self.status == "Paid":
			frappe.throw(
				_("A paid order cannot be cancelled. Raise a refund instead."),
				title=_("Already Paid"),
			)
