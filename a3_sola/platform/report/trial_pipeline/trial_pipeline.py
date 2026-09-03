# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Trial Pipeline.

Active trials with days remaining and the engagement signals that actually predict whether
one converts. Signals rather than a score: "has never signed in on day 11 of 14" is
something a person can act on this afternoon, and a number between 0 and 1 is not.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, today

from a3_sola.api.entitlements import TENANT_FIELD


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, _summary()


def get_columns():
	return [
		{"label": _("Subscription"), "fieldname": "name", "fieldtype": "Link", "options": "Platform Subscription", "width": 150},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 200},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 90},
		{"label": _("Trial Ends"), "fieldname": "trial_end_date", "fieldtype": "Date", "width": 105},
		{"label": _("Days Left"), "fieldname": "days_left", "fieldtype": "Int", "width": 90},
		{"label": _("Users Created"), "fieldname": "users", "fieldtype": "Int", "width": 110},
		{"label": _("Ever Signed In"), "fieldname": "signed_in", "fieldtype": "Int", "width": 115},
		{"label": _("Documents Created"), "fieldname": "documents", "fieldtype": "Int", "width": 140},
		{"label": _("Has a Mandate"), "fieldname": "has_mandate", "fieldtype": "Check", "width": 115},
		{"label": _("Signal"), "fieldname": "signal", "fieldtype": "Data", "width": 320},
		{"label": _("Contact"), "fieldname": "primary_contact_email", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	rows = []
	for sub in frappe.get_all(
		"Platform Subscription",
		filters={"status": "Trialing", "docstatus": ["<", 2]},
		fields=["name", "organisation_name", "plan_code", "trial_end_date",
		        "payment_mandate", "primary_contact_email"],
	):
		tenant = frappe.db.get_value("Tenant", {"platform_subscription": sub.name}, "name")
		users = frappe.get_all("User", filters={TENANT_FIELD: tenant} if tenant else {"name": ""},
		                       fields=["name", "last_login"])
		signed_in = len([u for u in users if u.last_login])
		documents = _documents(tenant)
		days_left = (
			date_diff(getdate(sub.trial_end_date), getdate(today()))
			if sub.trial_end_date else None
		)
		rows.append({
			**sub,
			"days_left": days_left,
			"users": len(users),
			"signed_in": signed_in,
			"documents": documents,
			"has_mandate": 1 if sub.payment_mandate else 0,
			"signal": _signal(days_left, signed_in, documents, bool(sub.payment_mandate)),
		})
	rows.sort(key=lambda r: (r["days_left"] if r["days_left"] is not None else 999))
	return rows


def _signal(days_left, signed_in, documents, has_mandate):
	if not signed_in:
		return _("nobody has ever signed in - call today, this one is lost otherwise")
	if not documents:
		return _("signed in but created nothing - they have not found a use for it yet")
	if days_left is not None and days_left <= 3 and not has_mandate:
		return _("engaged, {0} day(s) left and no payment method - ask for the card").format(
			max(0, days_left))
	if has_mandate:
		return _("engaged and ready to bill")
	return _("engaged, {0} document(s) created").format(documents)


def _documents(tenant):
	company = frappe.db.get_value("Tenant", tenant, "company") if tenant else None
	if not company:
		return 0
	total = 0
	for doctype in ("Solar Consumer", "Site Survey", "Solar Design Estimate",
	                "Solar Proposal", "Solar Installation"):
		if frappe.db.exists("DocType", doctype):
			total += frappe.db.count(doctype, {"company": company})
	return total


def _summary():
	converted = frappe.db.count("Subscription Event", {"event_type": "Activated",
	                                                   "from_state": "Trialing"})
	expired = frappe.db.count("Subscription Event", {"event_type": "Trial Ended"})
	active = frappe.db.count("Platform Subscription", {"status": "Trialing"})
	return [
		{"label": _("Active trials"), "value": active, "indicator": "Blue"},
		{"label": _("Converted"), "value": converted, "indicator": "Green"},
		{"label": _("Expired without converting"), "value": max(0, expired - converted),
		 "indicator": "Orange"},
	]
