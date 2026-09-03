# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cohort Retention.

Tenants grouped by the month they were provisioned, and how many were still paying one,
three, six and twelve months later - with revenue retention beside logo retention, since
a cohort can lose half its customers and grow its revenue.
"""

import frappe
from frappe import _
from frappe.utils import add_months, date_diff, flt, getdate, today

MILESTONES = (1, 3, 6, 12)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	columns = [
		{"label": _("Cohort"), "fieldname": "cohort", "fieldtype": "Data", "width": 110},
		{"label": _("Tenants"), "fieldname": "size", "fieldtype": "Int", "width": 90},
		{"label": _("Starting MRR"), "fieldname": "starting_mrr", "fieldtype": "Currency", "width": 130},
	]
	for month in MILESTONES:
		columns.append({"label": _("M{0} Logo %").format(month),
		                "fieldname": f"logo_{month}", "fieldtype": "Percent", "width": 100})
	for month in MILESTONES:
		columns.append({"label": _("M{0} Revenue %").format(month),
		                "fieldname": f"revenue_{month}", "fieldtype": "Percent", "width": 115})
	return columns


def get_data(filters):
	cohorts = {}
	for tenant in frappe.get_all(
		"Tenant", filters={"docstatus": ["<", 2]},
		fields=["name", "creation", "platform_subscription", "status"],
	):
		key = getdate(tenant.creation).strftime("%Y-%m")
		cohorts.setdefault(key, []).append(tenant)

	rows = []
	for key in sorted(cohorts, reverse=True):
		members = cohorts[key]
		start = getdate(f"{key}-01")
		starting_mrr = sum(_mrr(t.platform_subscription) for t in members)
		row = {"cohort": start.strftime("%b %Y"), "size": len(members),
		       "starting_mrr": flt(starting_mrr, 2)}
		for month in MILESTONES:
			at = add_months(start, month)
			if getdate(at) > getdate(today()):
				row[f"logo_{month}"] = None
				row[f"revenue_{month}"] = None
				continue
			alive = [t for t in members if _alive_at(t, at)]
			row[f"logo_{month}"] = flt(len(alive) * 100.0 / len(members), 1)
			retained = sum(_mrr(t.platform_subscription) for t in alive)
			row[f"revenue_{month}"] = (
				flt(retained * 100.0 / starting_mrr, 1) if starting_mrr else 0
			)
		rows.append(row)
	return rows


def _alive_at(tenant, at):
	"""Was this tenant still paying on that date?

	Read from the event log, not from the tenant's state today - which is the only way a
	historical cohort means anything - but from a copy of the log loaded once. This was
	two queries per tenant per milestone: four milestones and fifty tenants is four
	hundred queries to fill a table with four columns.
	"""
	timeline = _event_timeline().get(tenant.platform_subscription)
	if not timeline:
		return True
	ended = [t for kind, t in timeline if kind in ("Cancelled", "Terminated") and t <= at]
	if not ended:
		return True
	returned = [t for kind, t in timeline if kind == "Reactivated" and t <= at]
	# Came back after they left, rather than merely at some point.
	return bool(returned and max(returned) > max(ended))


def _event_timeline():
	"""{subscription: [(event_type, date)]} for the events that end or resume a tenancy."""
	cached = getattr(frappe.local, "_a3s_cohort_events", None)
	if cached is not None:
		return cached
	timeline = {}
	for row in frappe.get_all(
		"Subscription Event",
		filters={"event_type": ["in", ["Cancelled", "Terminated", "Reactivated"]],
		         "was_dry_run": 0},
		fields=["platform_subscription", "event_type", "event_time"],
	):
		timeline.setdefault(row.platform_subscription, []).append(
			(row.event_type, getdate(row.event_time))
		)
	frappe.local._a3s_cohort_events = timeline
	return timeline


def _mrr(subscription):
	"""From a table loaded once, not a query per tenant per milestone."""
	cached = getattr(frappe.local, "_a3s_cohort_mrr", None)
	if cached is None:
		cached = {}
		for row in frappe.get_all("Platform Subscription",
		                          fields=["name", "recurring_amount", "billing_cycle"]):
			amount = flt(row.recurring_amount)
			cached[row.name] = (
				flt(amount / 12.0, 2) if row.billing_cycle == "Annual" else amount
			)
		frappe.local._a3s_cohort_mrr = cached
	return cached.get(subscription, 0.0)
