# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Subscription Health.

One row per tenant, with a health score whose contributing factors are all shown beside
it. A bare number nobody can decompose gets ignored within a month, so every input to the
score is a column: seat use, days since anyone logged in, payment history and state.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, today

from a3_sola.api.entitlements import TENANT_FIELD


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 150},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 190},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 90},
		{"label": _("State"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Access"), "fieldname": "access_state", "fieldtype": "Data", "width": 90},
		{"label": _("Days in State"), "fieldname": "days_in_state", "fieldtype": "Int", "width": 105},
		{"label": _("MRR"), "fieldname": "mrr", "fieldtype": "Currency", "width": 110},
		{"label": _("Seats"), "fieldname": "seats", "fieldtype": "Data", "width": 80},
		{"label": _("Seat Use %"), "fieldname": "seat_use", "fieldtype": "Percent", "width": 100},
		{"label": _("Last Login"), "fieldname": "last_login", "fieldtype": "Date", "width": 105},
		{"label": _("Days Quiet"), "fieldname": "days_quiet", "fieldtype": "Int", "width": 95},
		{"label": _("Last Payment"), "fieldname": "last_payment", "fieldtype": "Date", "width": 110},
		{"label": _("Failures"), "fieldname": "failed_payments", "fieldtype": "Int", "width": 85},
		{"label": _("Open Tickets"), "fieldname": "open_tickets", "fieldtype": "Int", "width": 105},
		{"label": _("Health"), "fieldname": "health", "fieldtype": "Int", "width": 80},
		{"label": _("Why"), "fieldname": "health_reason", "fieldtype": "Data", "width": 320},
	]


def get_data(filters):
	"""One row per tenant, with every lookup batched.

	Read four to five queries per tenant - the subscription, the last login, the open
	tickets - which is how a report that looks instant on a demo site takes ten seconds on
	a real one.
	"""
	tenants = frappe.get_all(
		"Tenant",
		filters={"status": ["not in", ["Terminated"]]},
		fields=["name", "tenant_name", "platform_subscription", "user_quota",
		        "active_users", "company", "status"],
	)
	if not tenants:
		return []

	subscriptions = {
		row.name: row
		for row in frappe.get_all(
			"Platform Subscription",
			filters={"name": ["in", [t.platform_subscription for t in tenants
			                         if t.platform_subscription] or [""]]},
			fields=["name", "organisation_name", "plan_code", "status", "access_state",
			        "days_in_state", "recurring_amount", "billing_cycle",
			        "last_successful_billing_date", "failed_payments",
			        "consecutive_failures"],
		)
	}
	last_logins = _last_logins([t.name for t in tenants])
	open_tickets = _open_tickets_by_company([t.company for t in tenants if t.company])

	rows = []
	for tenant in tenants:
		subscription = subscriptions.get(tenant.platform_subscription) or frappe._dict()
		quota = cint(tenant.user_quota)
		used = cint(tenant.active_users)
		last_login = last_logins.get(tenant.name)
		quiet = date_diff(today(), getdate(last_login)) if last_login else None
		tickets = open_tickets.get(tenant.company, 0)
		mrr = _mrr(subscription)

		health, why = _score(subscription, quota, used, quiet, tickets)
		rows.append({
			"tenant": tenant.name,
			"organisation_name": subscription.get("organisation_name") or tenant.tenant_name,
			"plan_code": subscription.get("plan_code"),
			"status": subscription.get("status") or tenant.status,
			"access_state": subscription.get("access_state") or "Full",
			"days_in_state": cint(subscription.get("days_in_state")),
			"mrr": mrr,
			"seats": f"{used}/{quota}" if quota else str(used),
			"seat_use": flt(used * 100.0 / quota, 1) if quota else 0,
			"last_login": last_login,
			"days_quiet": quiet,
			"last_payment": subscription.get("last_successful_billing_date"),
			"failed_payments": cint(subscription.get("failed_payments")),
			"open_tickets": tickets,
			"health": health,
			"health_reason": why,
		})
	rows.sort(key=lambda r: (r["health"], -flt(r["mrr"])))
	return rows


def _last_logins(tenants):
	"""The most recent login per tenant, in one query rather than one each."""
	out = {}
	for row in frappe.get_all(
		"User", filters={TENANT_FIELD: ["in", tenants or [""]]},
		fields=[TENANT_FIELD, "last_login"], order_by="last_login desc",
	):
		tenant = row.get(TENANT_FIELD)
		if row.last_login and tenant not in out:
			out[tenant] = row.last_login
	return out


def _open_tickets_by_company(companies):
	if not companies or not frappe.db.exists("DocType", "Service Ticket"):
		return {}
	return {
		row["company"]: cint(row["n"])
		for row in frappe.get_all(
			"Service Ticket",
			filters={"company": ["in", companies],
			         "status": ["not in", ["Closed", "Cancelled", "Resolved"]]},
			fields=["company", "count(name) as n"], group_by="company",
		)
	}


def _score(subscription, quota, used, quiet, tickets):
	"""Out of 100, with every deduction named. The names are the point of the score."""
	score, reasons = 100, []
	state = subscription.get("status")
	if state in ("Suspended", "Cancelled"):
		score -= 60
		reasons.append(_("access blocked (-60)"))
	elif state == "Grace":
		score -= 35
		reasons.append(_("in grace (-35)"))
	elif state == "Past Due":
		score -= 20
		reasons.append(_("past due (-20)"))
	elif state == "Cancelling":
		score -= 50
		reasons.append(_("cancelling (-50)"))

	if quiet is None:
		score -= 25
		reasons.append(_("nobody has ever signed in (-25)"))
	elif quiet > 30:
		score -= 25
		reasons.append(_("no login for {0} days (-25)").format(quiet))
	elif quiet > 14:
		score -= 10
		reasons.append(_("no login for {0} days (-10)").format(quiet))

	if quota and used == 0:
		score -= 20
		reasons.append(_("no active users (-20)"))
	elif quota and (used * 100.0 / quota) < 40:
		score -= 8
		reasons.append(_("under 40% of seats used (-8)"))

	if cint(subscription.get("consecutive_failures")):
		score -= 15
		reasons.append(_("{0} consecutive payment failures (-15)").format(
			cint(subscription.get("consecutive_failures"))))
	if tickets > 3:
		score -= 8
		reasons.append(_("{0} open tickets (-8)").format(tickets))

	return max(0, score), "; ".join(reasons) or _("nothing wrong")


def _mrr(subscription):
	amount = flt(subscription.get("recurring_amount"))
	if (subscription.get("billing_cycle") or "Monthly") == "Annual":
		return flt(amount / 12.0, 2)
	return amount


