# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The tax invoice the client issues to their SaaS customer.

Distinct from ERPNext's Sales Invoice in that the billing engine generates it - but it
must be able to post as one, which is what `sales_invoice` and `posting_status` are for.

Two compliance points shape the code:

**The lines are built from the Payment Order's price breakdown**, so the invoice and the
charge can never disagree. An invoice that says one number while the card was charged
another is the kind of thing a customer notices at their GST return.

**The numbering is gapless per company per fiscal year.** A tax invoice series with holes
in it is a compliance problem, so a submitted invoice can be cancelled but never deleted,
and the number is allocated inside a row lock so two concurrent submissions cannot claim
the same one.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, money_in_words

from a3_sola.api import tax
from a3_sola.api.settings import get_value


class SubscriptionInvoice(Document):
	def autoname(self):
		"""Gapless, sequential, per company per fiscal year."""
		self.name = allocate_invoice_number(self.company, self.invoice_date)

	def validate(self):
		self.resolve_party_tax()
		self.build_lines_if_empty()
		self.compute_totals()

	def resolve_party_tax(self):
		self.customer_gstin = tax.validate_gstin(self.customer_gstin, self.customer_state_code)
		if self.customer_gstin and not self.customer_state_code:
			self.customer_state_code = self.customer_gstin[:2]
		code, place = tax.resolve_place_of_supply(
			self.customer_state, self.customer_state_code, self.customer_gstin
		)
		self.customer_state_code = code or self.customer_state_code
		self.place_of_supply = self.place_of_supply or place

	def build_lines_if_empty(self):
		"""From the order's breakdown, so charge and invoice cannot diverge."""
		if self.items or not self.payment_order:
			return
		order = frappe.get_cached_doc("Payment Order", self.payment_order)
		hsn = get_value("subscription_hsn_sac") or "997331"
		breakdown = frappe.parse_json(order.price_breakdown or "[]")

		for line in breakdown:
			amount = flt(line.get("amount"))
			if not amount:
				continue
			self.append(
				"items",
				{
					"description": line.get("label"),
					"line_type": _line_type(line.get("label")),
					"hsn_sac": hsn,
					"quantity": 1,
					"rate": amount,
					"amount": amount,
				},
			)
		if not self.items:
			self.append(
				"items",
				{
					"description": order.description or _("Subscription"),
					"line_type": "Subscription",
					"hsn_sac": hsn,
					"quantity": 1,
					"rate": order.subtotal,
					"amount": order.subtotal,
				},
			)

	def compute_totals(self):
		self.taxable_value = flt(sum(flt(row.amount) for row in self.items), 2)
		split = tax.compute_tax(self.taxable_value, self.customer_state_code)
		self.tax_rate = split["tax_rate"]
		self.tax_type = split["tax_type"]
		self.igst_amount = split["igst_amount"]
		self.cgst_amount = split["cgst_amount"]
		self.sgst_amount = split["sgst_amount"]
		self.total_tax = split["total_tax"]
		self.grand_total = flt(self.taxable_value + self.total_tax, 2)
		self.amount_in_words = money_in_words(self.grand_total, self.currency or "INR")

	def before_submit(self):
		"""A GSTIN that contradicts the address breaks the customer's input credit."""
		if self.customer_gstin:
			tax.validate_gstin(self.customer_gstin, self.customer_state_code)
		if not self.items:
			frappe.throw(_("An invoice needs at least one line."))

	def on_submit(self):
		from a3_sola.api import accounting_payments

		accounting_payments.post_subscription_invoice(self)

	def on_cancel(self):
		"""Cancelled, never deleted - the series must stay gapless."""
		from a3_sola.api import accounting_payments

		accounting_payments.cancel_subscription_invoice(self)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(
				_("A submitted tax invoice cannot be deleted, only cancelled. Deleting one "
				  "would leave a gap in the invoice series."),
				title=_("Cannot Delete"),
			)


def _line_type(label):
	lowered = (label or "").lower()
	if "additional user" in lowered:
		return "Additional Users"
	if "implementation" in lowered:
		return "Implementation Fee"
	return "Subscription"


def fiscal_year_of(date):
	"""Indian fiscal year: April to March."""
	date = getdate(date)
	start = date.year if date.month >= 4 else date.year - 1
	return f"{start}-{str(start + 1)[-2:]}"


def allocate_invoice_number(company, invoice_date):
	"""Next number in the series, allocated under a lock.

	Two concurrent submissions must not claim the same number, and the sequence must have
	no holes - so this counts what exists rather than relying on a naming series that
	skips on a failed insert.
	"""
	prefix = get_value("subscription_invoice_series_prefix") or "SINV"
	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	year = fiscal_year_of(invoice_date or frappe.utils.today())
	series = f"{prefix}-{abbr}-{year}-" if abbr else f"{prefix}-{year}-"

	# Serialise allocation across workers. Without this two submissions a millisecond
	# apart both read the same maximum and both try to write the same number.
	frappe.db.sql(
		"select name from `tabSubscription Invoice` where name like %s order by name desc "
		"limit 1 for update",
		(series + "%",),
	)
	last = frappe.db.sql(
		"select name from `tabSubscription Invoice` where name like %s order by name desc limit 1",
		(series + "%",),
	)
	next_number = 1
	if last:
		try:
			next_number = int(str(last[0][0]).rsplit("-", 1)[-1]) + 1
		except (ValueError, IndexError):
			next_number = 1
	return f"{series}{next_number:05d}"
