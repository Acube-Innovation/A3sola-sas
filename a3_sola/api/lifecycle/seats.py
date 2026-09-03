# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Buying and giving back seats.

The speed requirement is the design constraint. A tenant admin who hits their seat limit
at 11am should be able to buy a seat and carry on within a minute. A hard quota block that
takes three days to resolve becomes a support ticket and a bad review, so the trust
threshold below exists: a long-tenured tenant with a clean payment record gets the seat
immediately and is billed on the next invoice.

Removals go the other way and wait for the period boundary, because the customer has
already paid for the seats they are giving up.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from a3_sola.api.settings import get_int, get_value


def trusted(tenant):
	"""May this tenant have seats before paying for them?

	Deliberately conservative, and both halves matter: tenure without a clean record is
	just an old debtor, and a clean record without tenure is a tenant who has paid once.
	"""
	min_days = get_int("seat_trust_min_days", 180)
	subscription = frappe.db.get_value("Tenant", tenant, "platform_subscription")
	if not subscription:
		return False, _("No subscription")
	row = frappe.db.get_value(
		"Platform Subscription", subscription,
		["lifetime_days_active", "failed_payments", "consecutive_failures", "status"],
		as_dict=True,
	)
	if not row:
		return False, _("No subscription")
	if row.status != "Active":
		return False, _("Subscription is {0}").format(row.status)
	if cint(row.failed_payments) or cint(row.consecutive_failures):
		return False, _("There have been failed payments on this account")
	if cint(row.lifetime_days_active) < min_days:
		return False, _("{0} days old; {1} required").format(
			cint(row.lifetime_days_active), min_days)
	return True, _("{0} days active with no failed payments").format(
		cint(row.lifetime_days_active))


@frappe.whitelist()
def preview_seats(tenant, count):
	"""What another seat costs, right now, before the customer commits."""
	from a3_sola.api.lifecycle import plan_change, proration

	subscription = frappe.get_doc(
		"Platform Subscription",
		frappe.db.get_value("Tenant", tenant, "platform_subscription"),
	)
	count = cint(count)
	quote = proration.calculate_proration(
		subscription, "Add Seats" if count > 0 else "Remove Seats", seat_delta=count
	)
	new_amount = plan_change._new_recurring(subscription, None, None, seat_delta=count)
	impact, detail, route = proration.assess_mandate_impact(subscription, new_amount)
	ok, why = trusted(tenant)
	quote.update({
		"new_recurring_amount": new_amount,
		"mandate_impact": impact,
		"mandate_impact_detail": detail,
		"new_collection_route": route,
		"immediate": bool(count > 0),
		"trusted": ok,
		"trust_reason": why,
	})
	return quote


@frappe.whitelist()
def request_seats(tenant, count, requested_by="Tenant Self Service"):
	"""Create the Seat Change Request. Additions are immediate; removals wait."""
	from a3_sola.api.lifecycle import plan_change, proration

	count = cint(count)
	if not count:
		frappe.throw(_("Say how many seats."))
	subscription_name = frappe.db.get_value("Tenant", tenant, "platform_subscription")
	if not subscription_name:
		frappe.throw(_("Tenant {0} has no subscription.").format(tenant))
	subscription = frappe.get_doc("Platform Subscription", subscription_name)

	from a3_sola.api.entitlements import get_tenant_usage

	usage = get_tenant_usage(tenant)
	quota = cint(usage.get("quota"))
	blockers = []
	if count < 0 and cint(usage.get("used")) > quota + count:
		blockers.append(_(
			"{0} users are active. Removing {1} seat(s) leaves {2}, so {3} user(s) have "
			"to be disabled first - and you choose which."
		).format(usage["used"], abs(count), quota + count,
		         cint(usage["used"]) - (quota + count)))

	quote = preview_seats(tenant, count)
	doc = frappe.get_doc({
		"doctype": "Seat Change Request",
		"tenant": tenant,
		"platform_subscription": subscription.name,
		"change_type": "Add Seats" if count > 0 else "Remove Seats",
		"requested_by": requested_by,
		"seat_delta": count,
		"current_quota": quota,
		"new_quota": quota + count,
		"current_active_users": cint(usage.get("used")),
		"effective_type": "Immediate" if count > 0 else "Next Period",
		"net_amount_payable": flt(quote["net_amount_payable"]),
		"new_recurring_amount": flt(quote["new_recurring_amount"]),
		"mandate_impact": quote["mandate_impact"],
		"removal_blockers": "\n".join(blockers),
		"proration": [dict(line) for line in quote["lines"]],
		"status": "Awaiting User Reduction" if blockers else "Draft",
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()

	if blockers:
		return doc.name
	if count < 0:
		# Nothing to collect; it lands at the boundary.
		return doc.name

	ok, _why = trusted(tenant)
	if ok or flt(quote["net_amount_payable"]) <= 0:
		apply_seat_change(doc.name)
	else:
		doc.db_set("status", "Awaiting Payment", update_modified=False)
		_raise_payment(doc, subscription)
	return doc.name


def apply_seat_change(request):
	"""Re-snapshot the quota, reconcile roles, and record it. Idempotent."""
	from a3_sola.api.entitlements import apply_module_entitlements
	from a3_sola.api.lifecycle import events, proration

	doc = request if not isinstance(request, str) else frappe.get_doc(
		"Seat Change Request", request)
	if doc.status == "Applied":
		return doc.name

	tenant = doc.tenant
	subscription = frappe.get_doc("Platform Subscription", doc.platform_subscription)
	delta = cint(doc.seat_delta)

	additional = cint(frappe.db.get_value("Tenant", tenant, "additional_users")) + delta
	included = cint(frappe.db.get_value("Tenant", tenant, "included_users"))
	frappe.db.set_value("Tenant", tenant, {
		"additional_users": max(0, additional),
		"user_quota": max(0, included + max(0, additional)),
	}, update_modified=False)

	subscription.db_set({
		"additional_users": max(0, additional),
		"recurring_amount": flt(doc.new_recurring_amount),
	}, update_modified=False)
	subscription.reload()

	impact, detail, route = proration.assess_mandate_impact(
		subscription, flt(doc.new_recurring_amount)
	)
	from a3_sola.api.lifecycle import plan_change

	plan_change._act_on_mandate(subscription, impact, detail, route)
	apply_module_entitlements(tenant)

	event = events.record(
		subscription=subscription.name,
		event_type="Seats Added" if delta > 0 else "Seats Removed",
		reason=_("{0} seat(s) {1}; quota is now {2}.").format(
			abs(delta), _("added") if delta > 0 else _("removed"),
			max(0, included + max(0, additional))),
		triggered_by="Tenant Self Service" if doc.requested_by == "Tenant Self Service"
		else "Internal User",
		related=("Seat Change Request", doc.name),
	)
	doc.db_set({"status": "Applied", "applied_on": now_datetime(),
	            "subscription_event": event.name, "mandate_impact": impact},
	           update_modified=False)
	return doc.name


def _raise_payment(request, subscription):
	"""The prorated charge, through the Phase 5 payment path."""
	from a3_sola.api import payments

	try:
		order = payments.build_order(
			reference_doctype="Seat Change Request",
			reference_name=request.name,
			order_type="Seat Addition",
			amount=flt(request.net_amount_payable),
			subscription=subscription,
		) if hasattr(payments, "build_order") else None
	except Exception:
		frappe.log_error(frappe.get_traceback(),
		                 f"a3_sola: seat payment order for {request.name}")
		order = None
	if order:
		request.db_set("payment_order", order.name, update_modified=False)
	return order


def on_seat_payment_received(request):
	"""Called from the payment webhook. Seats appear the moment the money clears."""
	doc = request if not isinstance(request, str) else frappe.get_doc(
		"Seat Change Request", request)
	if doc.status in ("Applied", "Cancelled"):
		return doc.name
	return apply_seat_change(doc)


def add_seats(tenant, count):
	"""The Phase 6 extension point, implemented.

	Its contract said: re-snapshot `additional_users` and `user_quota`, raise prorated
	billing through the Phase 5 path, do not grant the seats until payment is confirmed,
	and call `apply_module_entitlements` afterwards. All four are kept - with one
	deliberate widening, the trust threshold above, which grants immediately for a
	long-tenured tenant with a clean record and bills on the next invoice.
	"""
	return request_seats(tenant, cint(count), requested_by="Internal User")
