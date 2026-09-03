# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Churn Analysis.

Cancellations by reason, plan, cycle and tenure - and revenue churn beside logo churn,
because losing one large customer and five small ones are very different months that look
identical on a count.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Request"), "fieldname": "name", "fieldtype": "Link", "options": "Cancellation Request", "width": 140},
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 190},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 170},
		{"label": _("In Their Words"), "fieldname": "reason_detail", "fieldtype": "Data", "width": 260},
		{"label": _("Competitor"), "fieldname": "competitor_named", "fieldtype": "Data", "width": 140},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 90},
		{"label": _("Cycle"), "fieldname": "billing_cycle", "fieldtype": "Data", "width": 80},
		{"label": _("Tenure (days)"), "fieldname": "tenure_days", "fieldtype": "Int", "width": 110},
		{"label": _("MRR Lost"), "fieldname": "mrr_lost", "fieldtype": "Currency", "width": 120},
		{"label": _("Retention Tried"), "fieldname": "retention_outcome", "fieldtype": "Data", "width": 130},
		{"label": _("Would Reconsider"), "fieldname": "would_reconsider", "fieldtype": "Check", "width": 130},
		{"label": _("Came Back"), "fieldname": "came_back", "fieldtype": "Check", "width": 100},
	]


def get_data(filters):
	rows = []
	for request in frappe.get_all(
		"Cancellation Request",
		filters={"docstatus": 1},
		fields=["name", "platform_subscription", "reason", "reason_detail",
		        "competitor_named", "would_reconsider", "retention_outcome",
		        "effective_date", "status"],
		order_by="effective_date desc",
	):
		sub = frappe.db.get_value(
			"Platform Subscription", request.platform_subscription,
			["organisation_name", "plan_code", "billing_cycle", "recurring_amount",
			 "start_date"], as_dict=True,
		) or frappe._dict()
		amount = flt(sub.get("recurring_amount"))
		if sub.get("billing_cycle") == "Annual":
			amount = flt(amount / 12.0, 2)
		rows.append({
			"name": request.name,
			"month": getdate(request.effective_date).strftime("%b %Y")
			if request.effective_date else "",
			"organisation_name": sub.get("organisation_name"),
			"reason": request.reason,
			"reason_detail": (request.reason_detail or "")[:200],
			"competitor_named": request.competitor_named,
			"plan_code": sub.get("plan_code"),
			"billing_cycle": sub.get("billing_cycle"),
			"tenure_days": date_diff(request.effective_date, sub.get("start_date"))
			if (request.effective_date and sub.get("start_date")) else 0,
			"mrr_lost": amount,
			"retention_outcome": request.retention_outcome,
			"would_reconsider": cint(request.would_reconsider),
			"came_back": 1 if request.status in ("Reactivated", "Withdrawn") else 0,
		})
	return rows
