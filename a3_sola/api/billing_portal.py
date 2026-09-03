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


# ---------------------------------------------------------- Phase 7: self-service
#
# Everything below is guarded by `assert_owns`, and the ones that change something also
# require the tenant's own admin role. A customer being able to read their own history is
# the point; an ordinary user of theirs being able to downgrade the plan is not.


def _session_tenant():
	"""The tenant the logged-in user belongs to, if any."""
	from a3_sola.api.entitlements import TENANT_FIELD

	if frappe.session.user in ("Guest", ""):
		return None
	return frappe.db.get_value("User", frappe.session.user, TENANT_FIELD)


def _assert_tenant_member(subscription):
	"""Read access for anyone who belongs to the tenant this subscription pays for.

	Deliberately separate from `assert_owns`, which is not widened. `assert_owns` gates
	invoices, mandates and payment, and those should stay with the billing contact and the
	linked Customer - a tenant's site engineer has no business downloading their employer's
	invoices. What this grants is the subscription's own state, the seat count, the team
	list and the event history: what somebody needs to understand why the banner at the top
	of their screen is there.
	"""
	tenant = frappe.db.get_value("Tenant", {"platform_subscription": subscription}, "name")
	if tenant and _session_tenant() == tenant:
		return tenant
	# Falls back to the billing-contact and Customer paths, so the person who opened the
	# subscription still reaches it even before a tenant exists.
	assert_owns(subscription)
	return tenant


def _assert_tenant_admin(subscription):
	"""The caller must administer the tenant this subscription belongs to."""
	from a3_sola.api.entitlements import TENANT_FIELD

	tenant = _assert_tenant_member(subscription)
	if not tenant:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	if frappe.db.get_value("Tenant", tenant, "admin_user") == frappe.session.user:
		return tenant

	# The second path: somebody the tenant has since made an administrator. Checked on the
	# role PROFILE, not on a role - "Solar Tenant Administrator" is a Role Profile, and
	# `frappe.get_roles()` would never contain it. Whichever profile the tenant was
	# provisioned with is the one that counts, so it is read from the tenant rather than
	# hardcoded.
	profile = frappe.db.get_value("Tenant", tenant, "assigned_role_profile")
	if profile and frappe.db.get_value("User", frappe.session.user, "role_profile_name") == profile:
		if frappe.db.get_value("User", frappe.session.user, TENANT_FIELD) == tenant:
			return tenant

	frappe.throw(
		_("Only your organisation's administrator can change the plan or the number of "
		  "seats. Ask them, or contact us."),
		frappe.PermissionError,
	)


@frappe.whitelist()
def my_plan(subscription):
	"""The current plan, what it costs, and when it renews."""
	_assert_tenant_member(subscription)
	doc = frappe.get_doc("Platform Subscription", subscription)
	tenant = frappe.db.get_value("Tenant", {"platform_subscription": subscription}, "name")
	usage = {}
	if tenant:
		from a3_sola.api.entitlements import get_tenant_usage

		usage = get_tenant_usage(tenant)
	return {
		"plan": doc.subscription_plan,
		"plan_code": doc.plan_code,
		"cycle": doc.billing_cycle,
		"amount": flt(doc.recurring_amount),
		"currency": doc.currency,
		"status": doc.status,
		"access_state": doc.access_state,
		"next_billing_date": doc.next_billing_date,
		"collection_route": doc.collection_route,
		"trial_end_date": doc.trial_end_date,
		"seats": usage,
		# Said plainly, because a customer who can see what happens next raises fewer
		# tickets than one who has to ask.
		"next_change_on": doc.next_state_change_on,
		"next_change_to": doc.next_state_change_to,
	}


@frappe.whitelist()
def available_plans(subscription):
	"""Every plan they could move to, with what each would cost them."""
	from a3_sola.api import platform

	_assert_tenant_member(subscription)
	doc = frappe.get_doc("Platform Subscription", subscription)
	out = []
	for plan in platform.get_published_plans():
		out.append({
			**plan,
			"is_current": plan.get("name") == doc.subscription_plan,
		})
	return out


@frappe.whitelist()
def preview_plan_change(subscription, new_plan=None, new_cycle=None):
	"""The proration and any consequence for how they pay - BEFORE they confirm.

	Nobody should agree to a figure they have not seen, and nobody should discover that
	their next renewal now needs authentication after it has failed at the bank.
	"""
	from a3_sola.api.lifecycle import plan_change

	_assert_tenant_member(subscription)
	return plan_change.preview(subscription, new_plan=new_plan, new_cycle=new_cycle)


@frappe.whitelist()
def change_my_plan(subscription, new_plan=None, new_cycle=None):
	_assert_tenant_admin(subscription)
	from a3_sola.api.lifecycle import plan_change

	return plan_change.request_change(subscription, new_plan=new_plan,
	                                  new_cycle=new_cycle,
	                                  requested_by="Tenant Self Service")


@frappe.whitelist()
def preview_seat_change(subscription, count):
	from a3_sola.api.lifecycle import seats

	tenant = _tenant_for(subscription)
	return seats.preview_seats(tenant, count)


@frappe.whitelist()
def change_my_seats(subscription, count):
	"""Buying a seat mid-workday should take under a minute, so this is the whole flow."""
	from a3_sola.api.lifecycle import seats

	tenant = _assert_tenant_admin(subscription)
	return seats.request_seats(tenant, count, requested_by="Tenant Self Service")


@frappe.whitelist()
def my_team(subscription):
	"""The user list with last activity - what a downgrade decision needs.

	The tenant chooses who to remove. Nothing here picks for them.
	"""
	from a3_sola.api.entitlements import TENANT_FIELD

	tenant = _tenant_for(subscription)
	return frappe.get_all(
		"User", filters={TENANT_FIELD: tenant},
		fields=["name", "full_name", "enabled", "last_login", "last_active"],
		order_by="last_active desc",
	)


@frappe.whitelist()
def my_history(subscription, limit=30):
	"""Their own subscription events, in language a customer can read.

	Internal detail is deliberately dropped: no policy stage codes, no actor, no dry-run
	rows. What is left is what happened and why.
	"""
	from a3_sola.api.lifecycle import events

	_assert_tenant_member(subscription)
	readable = []
	for row in events.history(subscription, limit=int(limit)):
		if row.get("was_dry_run"):
			continue
		if row.get("event_type") == "Policy Evaluated":
			continue
		readable.append({
			"when": row["event_time"],
			"what": row["event_type"],
			"why": row["reason"],
		})
	return readable


@frappe.whitelist()
def cancel_my_subscription(subscription, reason, reason_detail=None,
                           competitor_named=None, would_reconsider=0):
	"""End of period, always, from here. Immediate cancellation may involve a refund and
	is an internal decision."""
	from a3_sola.api.lifecycle import cancellation

	_assert_tenant_admin(subscription)
	return cancellation.request_cancellation(
		subscription, reason, reason_detail=reason_detail,
		cancellation_type="End of Period", requested_by="Tenant Self Service",
		competitor_named=competitor_named, would_reconsider=would_reconsider,
	)


@frappe.whitelist()
def reactivate_my_subscription(subscription):
	from a3_sola.api.lifecycle import cancellation

	_assert_tenant_admin(subscription)
	return cancellation.reactivate_subscription(subscription,
	                                            trigger="Tenant Self Service")


def _tenant_for(subscription):
	tenant = _assert_tenant_member(subscription)
	if not tenant:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	return tenant
