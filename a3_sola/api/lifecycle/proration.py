# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The one place any proration is computed. There is deliberately no second one.

Proration is where subscription bugs live, and they are the kind customers notice and
remember. So: one function, one rounding convention, an inspectable line-item breakdown
the customer sees before confirming, and hand-worked tests with exact expected paise.

THE DAY-COUNT CONVENTION, stated once and held to everywhere
------------------------------------------------------------
Calendar days, counted inclusively of the start and exclusively of the end:

    period_days   = (current_period_end - current_period_start) + 1
    days_used     = (effective_date - current_period_start)        # the days already had
    days_remaining= period_days - days_used

A 30-day period changed on its 11th day has used 10 and has 20 remaining. A February
period has 28 or 29 days and is prorated over that, not over a notional 30 - which is why
the leap-day case has its own test.

Money is rounded ONCE, at the line, to two decimals. Nothing accumulates at full precision
and rounds at the end, because that is how a breakdown stops adding up to its own total.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, today

from a3_sola.api import tax
from a3_sola.api.settings import get_value


def period_days(start, end):
	"""Inclusive of both ends. See the convention above."""
	return max(1, date_diff(getdate(end), getdate(start)) + 1)


def days_used(start, effective_date):
	return max(0, date_diff(getdate(effective_date), getdate(start)))


def daily_rate(amount, days):
	"""Full precision here on purpose - the rounding happens once, at the line."""
	return flt(amount) / max(1, days)


def calculate_proration(
	subscription,
	change_type,
	new_plan=None,
	new_cycle=None,
	seat_delta=0,
	effective_date=None,
):
	"""The full breakdown for a change. Returns a dict; writes nothing.

	`change_type` is one of Upgrade, Downgrade, Cycle Change, Plan Swap, Add Seats,
	Remove Seats.
	"""
	doc = _as_doc(subscription)
	effective_date = getdate(effective_date or today())
	start = getdate(doc.current_period_start or doc.start_date or today())
	end = getdate(doc.current_period_end or add_days(start, 29))

	total_days = period_days(start, end)
	used = min(days_used(start, effective_date), total_days)
	remaining = max(0, total_days - used)

	lines = []
	current_cycle = doc.billing_cycle
	target_cycle = new_cycle or current_cycle
	current_net = flt(doc.subtotal)  # ex-tax; tax is computed on the net change below

	if change_type in ("Upgrade", "Downgrade", "Plan Swap", "Cycle Change"):
		new_net = _plan_net(new_plan or doc.subscription_plan, target_cycle,
		                    cint(doc.additional_users))
		if change_type == "Downgrade" or (
			change_type == "Cycle Change" and target_cycle == "Monthly"
		):
			# Takes effect at the boundary, so nothing is prorated and nothing is
			# refunded. The customer keeps what they paid for until the period ends.
			lines.append(_line(
				"Adjustment",
				_("{0} takes effect on {1}, the start of your next billing period.").format(
					change_type, add_days(end, 1)),
				start=effective_date, end=end, days=remaining,
				full_period=new_net, prorated=0.0,
				notes=_("No charge and no refund now: you keep the plan you have paid for "
				        "until it expires."),
			))
		else:
			credit = flt(daily_rate(current_net, total_days) * remaining, 2)
			charge = flt(daily_rate(new_net, total_days) * remaining, 2)
			lines.append(_line(
				"Unused Credit",
				_("Unused {0} for {1} day(s)").format(doc.subscription_plan, remaining),
				start=effective_date, end=end, days=remaining,
				full_period=current_net, prorated=-credit,
			))
			lines.append(_line(
				"New Charge",
				_("{0} for the remaining {1} day(s)").format(
					new_plan or doc.subscription_plan, remaining),
				start=effective_date, end=end, days=remaining,
				full_period=new_net, prorated=charge,
			))
			if change_type == "Cycle Change" and target_cycle == "Annual":
				fee = _implementation_fee(new_plan or doc.subscription_plan)
				if fee:
					lines.append(_line(
						"Implementation Fee",
						_("Implementation fee waived on annual billing"),
						full_period=fee, prorated=0.0,
						notes=_("Waived: annual billing carries no implementation fee."),
					))

	if change_type in ("Add Seats", "Remove Seats") or seat_delta:
		per_seat = _seat_rate(doc.subscription_plan, target_cycle)
		count = abs(cint(seat_delta))
		amount = flt(daily_rate(per_seat * count, total_days) * remaining, 2)
		if cint(seat_delta) > 0:
			lines.append(_line(
				"Seat Charge",
				_("{0} additional seat(s) for the remaining {1} day(s)").format(count, remaining),
				start=effective_date, end=end, days=remaining, quantity=count,
				full_period=flt(per_seat * count, 2), prorated=amount,
			))
		elif cint(seat_delta) < 0:
			lines.append(_line(
				"Seat Credit",
				_("{0} seat(s) removed from {1}").format(count, add_days(end, 1)),
				start=add_days(end, 1), end=add_days(end, 1), days=0, quantity=count,
				full_period=flt(per_seat * count, 2), prorated=0.0,
				notes=_("Seat removals take effect at the period boundary; nothing is "
				        "refunded for the period already paid for."),
			))

	net = flt(sum(flt(line["prorated_amount"]) for line in lines), 2)
	split = tax.compute_tax(max(net, 0.0), doc.state_code)
	if net > 0 and split["total_tax"]:
		lines.append(_line(
			"Tax", _("{0} at {1}%").format(split["tax_type"], split["tax_rate"]),
			full_period=split["total_tax"], prorated=flt(split["total_tax"], 2),
		))

	gross = flt(net + (split["total_tax"] if net > 0 else 0.0), 2)
	payable = flt(max(gross, 0.0), 2)
	# A credit is carried against the next invoice, never refunded in cash from a plan
	# change. Cash refunds are an escalation with an approval, not a side effect.
	credit_forward = flt(abs(min(gross, 0.0)), 2)

	return {
		"change_type": change_type,
		"effective_date": effective_date,
		"period_start": start,
		"period_end": end,
		"period_days": total_days,
		"days_used": used,
		"days_remaining": remaining,
		"convention": (
			"Calendar days, inclusive of the period start and end. A change on day N of "
			"an M-day period has used N-1 days and has M-(N-1) remaining."
		),
		"lines": lines,
		"net_before_tax": net,
		"tax": split if net > 0 else {"total_tax": 0.0, "tax_type": split["tax_type"],
		                              "tax_rate": split["tax_rate"], "cgst_amount": 0.0,
		                              "sgst_amount": 0.0, "igst_amount": 0.0,
		                              "taxable_value": 0.0},
		"net_amount_payable": payable,
		"credit_carried_forward": credit_forward,
	}


def _line(line_type, description, start=None, end=None, days=0, full_period=0.0,
          prorated=0.0, quantity=1, notes=None):
	return {
		"line_type": line_type,
		"description": description,
		"from_date": getdate(start) if start else None,
		"to_date": getdate(end) if end else None,
		"days": cint(days),
		"full_period_amount": flt(full_period, 2),
		"prorated_amount": flt(prorated, 2),
		"quantity": flt(quantity),
		"notes": notes,
	}


# ------------------------------------------------------------------ plan pricing
def _plan_net(plan, cycle, additional_users=0):
	"""The ex-tax recurring amount for a plan on a cycle, including paid-for extra seats."""
	if not plan:
		return 0.0
	row = frappe.db.get_value(
		"Subscription Plan", plan,
		["monthly_price", "annual_price", "additional_user_price_monthly",
		 "additional_user_price_annual"],
		as_dict=True,
	) or frappe._dict()
	if (cycle or "Monthly") == "Annual":
		base = flt(row.get("annual_price"))
		per_seat = flt(row.get("additional_user_price_annual"))
	else:
		base = flt(row.get("monthly_price"))
		per_seat = flt(row.get("additional_user_price_monthly"))
	return flt(base + per_seat * cint(additional_users), 2)


def _seat_rate(plan, cycle):
	if not plan:
		return 0.0
	row = frappe.db.get_value(
		"Subscription Plan", plan,
		["additional_user_price_monthly", "additional_user_price_annual"], as_dict=True,
	) or frappe._dict()
	if (cycle or "Monthly") == "Annual":
		return flt(row.get("additional_user_price_annual"))
	return flt(row.get("additional_user_price_monthly"))


def _implementation_fee(plan):
	if not plan:
		return 0.0
	return flt(frappe.db.get_value("Subscription Plan", plan, "implementation_fee") or 0)


# --------------------------------------------------------------- mandate impact
def assess_mandate_impact(subscription, new_recurring_amount):
	"""Will this change break next month's collection? Answered before it is applied.

	Two separate things can go wrong, and both are silent until the bank declines:

	1. The registered mandate maximum is now too low, so the debit is refused.
	2. The amount has crossed the RBI no-AFA ceiling, so a silent auto-debit is no longer
	   permitted at all and the subscription has to be re-routed to an authenticated
	   renewal.

	Returns (impact, detail, new_route).
	"""
	from a3_sola.api import payments

	doc = _as_doc(subscription)
	amount = flt(new_recurring_amount, 2)
	route, why = payments.classify_collection(amount, doc.billing_cycle)
	new_route = "Auto Debit" if route == "Auto Debit" else "Assisted Renewal"

	mandate = doc.payment_mandate
	registered_max = flt(
		frappe.db.get_value("Payment Mandate", mandate, "registered_max_amount") if mandate else 0
	)

	if new_route != (doc.collection_route or "Auto Debit"):
		return (
			"Requires Route Change",
			_("The new recurring amount of {0} moves this subscription from {1} to {2}. "
			  "{3}").format(
				frappe.utils.fmt_money(amount, currency=doc.currency or "INR"),
				doc.collection_route or "Auto Debit", new_route, why),
			new_route,
		)
	if mandate and registered_max and amount > registered_max:
		return (
			"Requires New Maximum",
			_("The new recurring amount of {0} is above the {1} registered on mandate "
			  "{2}. The next auto-debit would be declined by the bank, so the mandate "
			  "has to be re-registered with a higher maximum before the next billing "
			  "date.").format(
				frappe.utils.fmt_money(amount, currency=doc.currency or "INR"),
				frappe.utils.fmt_money(registered_max, currency=doc.currency or "INR"),
				mandate),
			new_route,
		)
	if new_route == "Auto Debit" and not mandate:
		return (
			"Requires Re-registration",
			_("This subscription collects by auto debit but has no active mandate."),
			new_route,
		)
	return "None", "", new_route


def _as_doc(subscription):
	if isinstance(subscription, str):
		return frappe.get_doc("Platform Subscription", subscription)
	return subscription
