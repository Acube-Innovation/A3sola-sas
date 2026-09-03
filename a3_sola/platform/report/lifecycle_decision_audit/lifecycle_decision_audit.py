# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Lifecycle Decision Audit.

Every event over a period, with from-state, to-state, trigger, actor, reason and whether it
was a dry run. This is the report that answers "why was this customer suspended" in one
search, and it is the whole reason the event log is append-only.
"""

import frappe
from frappe import _
from frappe.utils import add_days, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("When"), "fieldname": "event_time", "fieldtype": "Datetime", "width": 155},
		{"label": _("Event"), "fieldname": "event_type", "fieldtype": "Data", "width": 150},
		{"label": _("Subscription"), "fieldname": "platform_subscription", "fieldtype": "Link", "options": "Platform Subscription", "width": 145},
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 130},
		{"label": _("From"), "fieldname": "from_state", "fieldtype": "Data", "width": 95},
		{"label": _("To"), "fieldname": "to_state", "fieldtype": "Data", "width": 95},
		{"label": _("Access Applied"), "fieldname": "access_effect_applied", "fieldtype": "Data", "width": 115},
		{"label": _("Trigger"), "fieldname": "triggered_by", "fieldtype": "Data", "width": 110},
		{"label": _("Actor"), "fieldname": "actor", "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Policy Stage"), "fieldname": "policy_stage", "fieldtype": "Data", "width": 105},
		{"label": _("Dry Run"), "fieldname": "was_dry_run", "fieldtype": "Check", "width": 80},
		{"label": _("At Risk"), "fieldname": "amount_at_risk", "fieldtype": "Currency", "width": 110},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 400},
		{"label": _("Event"), "fieldname": "name", "fieldtype": "Link", "options": "Subscription Event", "width": 140},
	]


def get_data(filters):
	conditions = {}
	if filters.get("from_date") or filters.get("to_date"):
		conditions["event_time"] = ["between", [
			filters.get("from_date") or add_days(today(), -30),
			filters.get("to_date") or today(),
		]]
	if filters.get("platform_subscription"):
		conditions["platform_subscription"] = filters.platform_subscription
	if filters.get("tenant"):
		conditions["tenant"] = filters.tenant
	if filters.get("event_type"):
		conditions["event_type"] = filters.event_type
	if filters.get("exclude_dry_run"):
		conditions["was_dry_run"] = 0

	return frappe.get_all(
		"Subscription Event",
		filters=conditions,
		fields=["name", "event_time", "event_type", "platform_subscription", "tenant",
		        "from_state", "to_state", "access_effect_applied", "triggered_by", "actor",
		        "policy_stage", "was_dry_run", "amount_at_risk", "reason"],
		order_by="event_time desc, creation desc",
		limit=2000,
	)
