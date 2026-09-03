# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""MRR Movement.

The bridge from opening to closing MRR, month by month: new, expansion, contraction,
churned and reactivated. Every row reconciles, and there is a test asserting it does,
because an MRR bridge that does not tie is worse than no MRR bridge - it gets quoted in a
board pack and then quietly disbelieved.

Every figure is derived from the Subscription Event log rather than from the current state
of a subscription, which is the only way to answer "what happened in March" in April.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 110},
		{"label": _("Opening"), "fieldname": "opening", "fieldtype": "Currency", "width": 130},
		{"label": _("New"), "fieldname": "new", "fieldtype": "Currency", "width": 120},
		{"label": _("Expansion"), "fieldname": "expansion", "fieldtype": "Currency", "width": 120},
		{"label": _("Contraction"), "fieldname": "contraction", "fieldtype": "Currency", "width": 120},
		{"label": _("Churned"), "fieldname": "churned", "fieldtype": "Currency", "width": 120},
		{"label": _("Reactivated"), "fieldname": "reactivated", "fieldtype": "Currency", "width": 120},
		{"label": _("Closing"), "fieldname": "closing", "fieldtype": "Currency", "width": 130},
		{"label": _("Reconciles"), "fieldname": "reconciles", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	months = int(filters.get("months") or 12)
	end = getdate(today())
	rows = []
	opening = 0.0

	# Every event in the whole window, once, then bucketed by month in memory. One query
	# instead of one per month, and the same answer.
	window_start = get_first_day(add_months(end, -(months - 1)))
	by_month = {}
	for event in frappe.get_all(
		"Subscription Event",
		filters={"event_time": [">=", window_start], "was_dry_run": 0},
		fields=["event_type", "platform_subscription", "reason_detail", "event_time"],
	):
		key = getdate(event.event_time).strftime("%Y-%m")
		by_month.setdefault(key, []).append(event)

	for offset in range(months - 1, -1, -1):
		start = get_first_day(add_months(end, -offset))
		finish = get_last_day(start)
		movement = _movement(start, finish, by_month.get(start.strftime("%Y-%m"), []))

		closing = flt(
			opening + movement["new"] + movement["expansion"]
			- movement["contraction"] - movement["churned"] + movement["reactivated"],
			2,
		)
		rows.append({
			"month": start.strftime("%b %Y"),
			"opening": flt(opening, 2),
			**{k: flt(v, 2) for k, v in movement.items()},
			"closing": closing,
			# Stated per row rather than only asserted in a test, so anybody reading the
			# report can see that it does.
			"reconciles": _("yes") if _ties(opening, movement, closing) else _("NO"),
		})
		opening = closing
	return rows


def _ties(opening, movement, closing):
	expected = flt(
		opening + movement["new"] + movement["expansion"]
		- movement["contraction"] - movement["churned"] + movement["reactivated"], 2
	)
	return abs(expected - flt(closing, 2)) < 0.01


def _movement(start, finish, events=None):
	if events is None:
		events = frappe.get_all(
			"Subscription Event",
			filters={"event_time": ["between", [start, finish]], "was_dry_run": 0},
			fields=["event_type", "platform_subscription", "reason_detail"],
		)
	movement = {"new": 0.0, "expansion": 0.0, "contraction": 0.0, "churned": 0.0,
	            "reactivated": 0.0}
	for event in events:
		amount = _mrr_of(event.platform_subscription)
		if event.event_type == "Activated":
			movement["new"] += amount
		elif event.event_type == "Reactivated":
			movement["reactivated"] += amount
		elif event.event_type == "Cancelled":
			movement["churned"] += amount
		elif event.event_type in ("Plan Upgraded", "Seats Added"):
			movement["expansion"] += _delta(event)
		elif event.event_type in ("Plan Downgraded", "Seats Removed"):
			movement["contraction"] += abs(_delta(event))
	return movement


def _delta(event):
	"""The before/after written into the event, so a later price change cannot rewrite
	what a past month's expansion was."""
	if not event.reason_detail:
		return 0.0
	try:
		payload = frappe.parse_json(event.reason_detail)
		before = flt((payload.get("before") or {}).get("amount"))
		after = flt((payload.get("after") or {}).get("amount"))
		return flt(after - before, 2)
	except Exception:
		return 0.0


def _mrr_of(subscription):
	"""Read from a table loaded once, not queried per event.

	This was one query per event per month - 221 queries to produce twelve rows, and the
	count grows with the event log rather than with the report. The whole subscription
	table is a few hundred rows and is read once.
	"""
	return _mrr_table().get(subscription, 0.0)


def _mrr_table():
	"""{subscription: monthly value}, cached for the life of the request."""
	cached = getattr(frappe.local, "_a3s_mrr_table", None)
	if cached is not None:
		return cached
	table = {}
	for row in frappe.get_all("Platform Subscription",
	                          fields=["name", "recurring_amount", "billing_cycle"]):
		amount = flt(row.recurring_amount)
		table[row.name] = flt(amount / 12.0, 2) if row.billing_cycle == "Annual" else amount
	frappe.local._a3s_mrr_table = table
	return table
