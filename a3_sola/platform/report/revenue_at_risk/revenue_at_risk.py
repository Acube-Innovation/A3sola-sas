# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Revenue at Risk.

The report the client opens every morning. Sorted by lifetime value rather than by how
overdue the account is, because ten days late on your largest customer is a call to make
before thirty days late on your smallest.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, today

AT_RISK = ("Past Due", "Grace", "Suspended", "Cancelling")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Subscription"), "fieldname": "name", "fieldtype": "Link", "options": "Platform Subscription", "width": 150},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 190},
		{"label": _("State"), "fieldname": "status", "fieldtype": "Data", "width": 95},
		{"label": _("Access"), "fieldname": "access_state", "fieldtype": "Data", "width": 85},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 120},
		{"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 110},
		{"label": _("Dunning Stage"), "fieldname": "dunning_stage", "fieldtype": "Data", "width": 120},
		{"label": _("Policy Stage"), "fieldname": "policy_stage", "fieldtype": "Data", "width": 110},
		{"label": _("Next Change"), "fieldname": "next_state_change_on", "fieldtype": "Date", "width": 110},
		{"label": _("Becomes"), "fieldname": "next_state_change_to", "fieldtype": "Data", "width": 100},
		{"label": _("Lifetime Value"), "fieldname": "lifetime_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Contact"), "fieldname": "primary_contact_email", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	rows = []
	for sub in frappe.get_all(
		"Platform Subscription",
		filters={"status": ["in", AT_RISK], "docstatus": ["<", 2]},
		fields=["name", "organisation_name", "status", "access_state", "recurring_amount",
		        "next_billing_date", "current_policy_stage", "next_state_change_on",
		        "next_state_change_to", "lifetime_value", "primary_contact_email"],
	):
		outstanding = _outstanding(sub.name) or flt(sub.recurring_amount)
		overdue = (
			max(0, date_diff(today(), getdate(sub.next_billing_date)))
			if sub.next_billing_date else 0
		)
		rows.append({
			**sub,
			"outstanding": outstanding,
			"days_overdue": overdue,
			"dunning_stage": _dunning_stage(sub.name),
			"policy_stage": sub.current_policy_stage,
		})
	rows.sort(key=lambda r: (-flt(r["lifetime_value"]), -flt(r["outstanding"])))
	return rows


def _outstanding(subscription):
	rows = frappe.get_all(
		"Subscription Invoice",
		filters={"platform_subscription": subscription,
		         "payment_status": ["in", ["Unpaid", "Partially Paid"]],
		         "docstatus": ["<", 2]},
		fields=["grand_total", "paid_amount"],
	)
	return flt(sum(flt(r.grand_total) - flt(r.paid_amount) for r in rows), 2)


def _dunning_stage(subscription):
	rows = frappe.get_all(
		"Dunning Attempt", filters={"parent": subscription},
		fields=["attempt_number", "attempt_type", "outcome"],
		order_by="idx desc", limit=1,
	)
	if not rows:
		return _("not started")
	return _("attempt {0}: {1} ({2})").format(
		cint(rows[0].attempt_number), rows[0].attempt_type or "",
		rows[0].outcome or _("pending"))
