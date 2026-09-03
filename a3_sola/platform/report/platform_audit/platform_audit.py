# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One trail across everything that is worth being able to answer for.

The audit evidence in this product is spread across four places by design - the hash
chained Platform Audit Entry, Phase 7's immutable Subscription Event, the Access
Suspension register and the ledger postings. That is right for writing; it is wrong for
answering "what happened to this customer's account", because nobody wants to search four
lists.

This unifies them for reading only. It writes nothing and it is the report you produce
when a customer asks what happened, or an auditor asks how a figure arose.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("When"), "fieldname": "when", "fieldtype": "Datetime", "width": 155},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 130},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 175},
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 130},
		{"label": _("Subject"), "fieldname": "subject", "fieldtype": "Data", "width": 300},
		{"label": _("Actor"), "fieldname": "actor", "fieldtype": "Data", "width": 175},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 340},
		{"label": _("Record"), "fieldname": "record", "fieldtype": "Dynamic Link", "options": "record_doctype", "width": 160},
		{"label": _("Record Doctype"), "fieldname": "record_doctype", "fieldtype": "Data", "hidden": 1},
	]


def get_data(filters):
	from_date = filters.get("from_date") or add_days(today(), -90)
	to_date = filters.get("to_date") or today()
	tenant = filters.get("tenant")
	wanted = filters.get("source")

	rows = []
	if not wanted or wanted == "Payments and Settings":
		rows += _audit_entries(from_date, to_date, filters)
	if not wanted or wanted == "Subscription Lifecycle":
		rows += _subscription_events(from_date, to_date, tenant, filters)
	if not wanted or wanted == "Access Suspensions":
		rows += _suspensions(from_date, to_date, tenant)
	if not wanted or wanted == "Entitlement Changes":
		rows += _entitlement_changes(from_date, to_date, tenant)

	if tenant:
		rows = [r for r in rows if not r.get("tenant") or r["tenant"] == tenant]
	if filters.get("actor"):
		rows = [r for r in rows if filters["actor"] in (r.get("actor") or "")]
	rows.sort(key=lambda r: str(r.get("when") or ""), reverse=True)
	return rows


def _audit_entries(from_date, to_date, filters):
	"""The hash-chained trail: refunds, manual overrides, credential and mode changes."""
	out = []
	for row in frappe.get_all(
		"Platform Audit Entry",
		filters={"creation": ["between", [from_date, to_date]]},
		fields=["name", "creation", "entry_type", "subject", "reason", "amount",
		        "reference_doctype", "reference_name", "owner", "platform_subscription"],
		order_by="creation desc", limit=3000,
	):
		out.append({
			"when": row.creation, "source": "Audit Entry", "action": row.entry_type,
			"tenant": _tenant_of_subscription(row.platform_subscription),
			"subject": row.subject, "actor": row.owner, "amount": flt(row.amount),
			"reason": row.reason,
			"record": row.reference_name or row.name,
			"record_doctype": row.reference_doctype or "Platform Audit Entry",
		})
	return out


def _subscription_events(from_date, to_date, tenant, filters):
	"""Phase 7's immutable log: every access and state change."""
	conditions = {"event_time": ["between", [from_date, to_date]]}
	if tenant:
		conditions["tenant"] = tenant
	if filters.get("exclude_dry_run"):
		conditions["was_dry_run"] = 0
	out = []
	for row in frappe.get_all(
		"Subscription Event", filters=conditions,
		fields=["name", "event_time", "event_type", "tenant", "from_state", "to_state",
		        "reason", "actor", "amount_at_risk", "was_dry_run",
		        "platform_subscription"],
		order_by="event_time desc", limit=3000,
	):
		subject = row.event_type
		if row.from_state or row.to_state:
			subject = f"{row.from_state or '—'} → {row.to_state or '—'}"
		if row.was_dry_run:
			subject += "  (dry run)"
		out.append({
			"when": row.event_time, "source": "Lifecycle", "action": row.event_type,
			"tenant": row.tenant, "subject": subject, "actor": row.actor,
			"amount": flt(row.amount_at_risk), "reason": row.reason,
			"record": row.name, "record_doctype": "Subscription Event",
		})
	return out


def _suspensions(from_date, to_date, tenant):
	conditions = {"creation": ["between", [from_date, to_date]]}
	if tenant:
		conditions["tenant"] = tenant
	out = []
	for row in frappe.get_all(
		"Access Suspension", filters=conditions,
		fields=["name", "creation", "tenant", "status", "reason", "outstanding_amount",
		        "approved_by", "users_disabled_count", "restored_on"],
		order_by="creation desc", limit=1000,
	):
		out.append({
			"when": row.creation, "source": "Suspension", "action": row.status,
			"tenant": row.tenant,
			"subject": _("{0} user(s) affected{1}").format(
				row.users_disabled_count or 0,
				_(", restored {0}").format(row.restored_on) if row.restored_on else ""),
			"actor": row.approved_by, "amount": flt(row.outstanding_amount),
			"reason": row.reason, "record": row.name,
			"record_doctype": "Access Suspension",
		})
	return out


def _entitlement_changes(from_date, to_date, tenant):
	"""Plan and seat changes - what a customer is entitled to, and when it changed."""
	out = []
	for doctype, action in (("Plan Change Request", "Plan change"),
	                        ("Seat Change Request", "Seat change")):
		if not frappe.db.exists("DocType", doctype):
			continue
		conditions = {"creation": ["between", [from_date, to_date]]}
		if tenant:
			conditions["tenant"] = tenant
		fields = ["name", "creation", "tenant", "status", "owner",
		          "net_amount_payable", "applied_on"]
		fields += (["request_type", "current_plan", "new_plan"]
		           if doctype == "Plan Change Request"
		           else ["change_type", "seat_delta", "new_quota"])
		for row in frappe.get_all(doctype, filters=conditions, fields=fields,
		                          order_by="creation desc", limit=1000):
			if doctype == "Plan Change Request":
				subject = f"{row.request_type}: {row.current_plan} → {row.new_plan}"
			else:
				subject = _("{0}: {1} seat(s), quota now {2}").format(
					row.change_type, row.seat_delta, row.new_quota)
			out.append({
				"when": row.creation, "source": action, "action": row.status,
				"tenant": row.tenant, "subject": subject, "actor": row.owner,
				"amount": flt(row.net_amount_payable),
				"reason": _("Applied {0}").format(row.applied_on) if row.applied_on
				else _("not applied"),
				"record": row.name, "record_doctype": doctype,
			})
	return out


def _tenant_of_subscription(subscription):
	if not subscription:
		return None
	return frappe.db.get_value("Tenant", {"platform_subscription": subscription}, "name")
