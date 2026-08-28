# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The subscribed customer's own billing pages.

Same rule as the Phase 3 customer portal: ownership is re-derived from the logged-in user
on every request and never taken from a URL parameter. A customer sees their own
subscription, their own invoices and their own mandate, and nothing internal - no gateway
ids beyond the payment reference, no cost, no internal notes.
"""

import frappe
from frappe import _
from frappe.utils import flt


def _customers():
	"""Every Customer the logged-in user is actually linked to."""
	user = frappe.session.user
	if user in ("Guest", ""):
		return []
	contacts = frappe.get_all(
		"Contact Email", filters={"email_id": user}, pluck="parent", distinct=True
	) or [""]
	linked = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"link_doctype": "Customer",
			"parent": ["in", contacts],
		},
		pluck="link_name",
		distinct=True,
	)
	portal = frappe.get_all(
		"Portal User", filters={"user": user, "parenttype": "Customer"}, pluck="parent"
	)
	return sorted(set(linked) | set(portal or []))


def _own_subscriptions():
	customers = _customers()
	user = frappe.session.user
	filters = {"docstatus": 1}
	names = set()
	if customers:
		names |= set(
			frappe.get_all(
				"Platform Subscription",
				filters={**filters, "customer": ["in", customers]},
				pluck="name",
			)
		)
	# A subscriber who has no Customer record yet is still identified by the address the
	# subscription was opened with.
	if user not in ("Guest", ""):
		names |= set(
			frappe.get_all(
				"Platform Subscription",
				filters={**filters, "primary_contact_email": user},
				pluck="name",
			)
		)
	return sorted(names)


def assert_owns(name):
	if name in _own_subscriptions():
		return name
	# Indistinguishable from a record that does not exist.
	frappe.throw(_("Not found"), frappe.DoesNotExistError)


def my_subscriptions():
	"""What the billing page renders. Nothing internal."""
	out = []
	for name in _own_subscriptions():
		row = frappe.db.get_value(
			"Platform Subscription",
			name,
			[
				"name", "organisation_name", "plan_code", "billing_cycle", "status",
				"included_users", "additional_users", "total_users", "recurring_amount",
				"currency", "current_period_start", "current_period_end",
				"next_billing_date", "collection_route", "route_reason", "payment_mandate",
			],
			as_dict=True,
		)
		if not row:
			continue
		row["plan_name"] = frappe.db.get_value(
			"Subscription Plan", {"plan_code": row.plan_code}, "plan_name"
		)
		row["mandate"] = _mandate_summary(row.payment_mandate)
		# The internal link is not the customer's business.
		row.pop("payment_mandate", None)
		out.append(row)
	return out


def _mandate_summary(name):
	if not name:
		return None
	row = frappe.db.get_value(
		"Payment Mandate",
		name,
		["status", "mandate_type", "instrument_masked", "bank_or_issuer",
		 "registered_max_amount", "valid_until"],
		as_dict=True,
	)
	return row


def my_invoices(subscription=None):
	"""Invoice history. Guarded by what the caller actually owns."""
	owned = _own_subscriptions()
	if subscription:
		assert_owns(subscription)
		owned = [subscription]
	if not owned:
		return []
	return frappe.get_all(
		"Subscription Invoice",
		filters={"platform_subscription": ["in", owned], "docstatus": 1},
		fields=[
			"name", "invoice_date", "period_start", "period_end", "taxable_value",
			"tax_type", "total_tax", "grand_total", "payment_status", "paid_on",
		],
		order_by="invoice_date desc",
		limit_page_length=50,
	)


@frappe.whitelist()
def download_invoice(invoice):
	"""Resolve an invoice only after proving the caller owns its subscription."""
	row = frappe.db.get_value(
		"Subscription Invoice", invoice, ["platform_subscription", "docstatus"], as_dict=True
	)
	if not row or row.docstatus != 1:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	assert_owns(row.platform_subscription)
	return {"print_url": f"/api/method/frappe.utils.print_format.download_pdf"
	                     f"?doctype=Subscription%20Invoice&name={invoice}"}


@frappe.whitelist()
def cancel_my_mandate(subscription, reason=None):
	"""The customer's own cancellation route.

	The framework requires customers to be able to cancel at any time and requires it to
	be honoured immediately.
	"""
	assert_owns(subscription)
	doc = frappe.get_doc("Platform Subscription", subscription)
	if not doc.payment_mandate:
		return {"ok": True, "message": _("There is no automatic payment to cancel.")}

	mandate = frappe.get_doc("Payment Mandate", doc.payment_mandate)
	mandate.set_status(
		"Cancelled",
		reason=(reason or _("Cancelled by the customer from their billing page."))[:200],
		source="Customer",
	)
	doc.db_set(
		{
			"collection_route": "Assisted Renewal",
			"route_reason": _("You cancelled the automatic payment, so we will send you a "
			                  "link to pay before each renewal."),
		},
		update_modified=False,
	)
	return {
		"ok": True,
		"message": _(
			"Your automatic payment is cancelled. Nothing further will be debited "
			"automatically, and we will send you a link before each renewal."
		),
	}


@frappe.whitelist()
def pay_outstanding(subscription):
	"""A pay-now link for an outstanding invoice."""
	assert_owns(subscription)
	order = frappe.db.get_value(
		"Payment Order",
		{"platform_subscription": subscription, "status": ["in", ["Created", "Pending", "Failed"]]},
		["name", "gateway_payment_link_url", "total_amount", "currency"],
		as_dict=True,
		order_by="creation desc",
	)
	if not order:
		return {"ok": True, "nothing_due": True, "message": _("There is nothing outstanding.")}
	return {
		"ok": True,
		"nothing_due": False,
		"amount": flt(order.total_amount),
		"currency": order.currency,
		"pay_url": order.gateway_payment_link_url,
	}
