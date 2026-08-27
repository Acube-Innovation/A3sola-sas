# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Acquisition Source Performance.

Which channels bring people who actually verify, and which bring volume that evaporates.
Demo requests are counted alongside signups because a channel that produces demos rather
than self-serve signups is not a worse channel, just a different one.
"""

import frappe
from frappe import _
from frappe.utils import flt

PAID = ("Paid", "Provisioning", "Active")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Source"), "fieldname": "utm_source", "fieldtype": "Data", "width": 140},
		{"label": _("Medium"), "fieldname": "utm_medium", "fieldtype": "Data", "width": 120},
		{"label": _("Campaign"), "fieldname": "utm_campaign", "fieldtype": "Data", "width": 170},
		{"label": _("Signups"), "fieldname": "signups", "fieldtype": "Int", "width": 100},
		{"label": _("Verified"), "fieldname": "verified", "fieldtype": "Int", "width": 100},
		{"label": _("Verification %"), "fieldname": "verification_rate", "fieldtype": "Percent", "width": 140},
		{"label": _("Paid"), "fieldname": "paid", "fieldtype": "Int", "width": 90},
		{"label": _("Conversion %"), "fieldname": "conversion_rate", "fieldtype": "Percent", "width": 140},
		{"label": _("Demo Requests"), "fieldname": "demos", "fieldtype": "Int", "width": 140},
		{"label": _("Pipeline Value"), "fieldname": "value", "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["creation"] = ["between", [filters.from_date, filters.to_date]]

	grouped = {}

	def bucket(row):
		key = (row.utm_source or "direct", row.utm_medium or "-", row.utm_campaign or "-")
		return grouped.setdefault(
			key,
			{"utm_source": key[0], "utm_medium": key[1], "utm_campaign": key[2],
			 "signups": 0, "verified": 0, "paid": 0, "demos": 0, "value": 0.0},
		)

	for row in frappe.get_all(
		"Subscription Signup",
		filters=conditions,
		fields=["utm_source", "utm_medium", "utm_campaign", "status", "is_email_verified",
		        "total_amount"],
		limit_page_length=0,
	):
		entry = bucket(row)
		entry["signups"] += 1
		entry["verified"] += 1 if row.is_email_verified else 0
		entry["paid"] += 1 if row.status in PAID else 0
		entry["value"] += flt(row.total_amount)

	demo_conditions = {}
	if filters.get("from_date") and filters.get("to_date"):
		demo_conditions["creation"] = ["between", [filters.from_date, filters.to_date]]
	for row in frappe.get_all(
		"Demo Request",
		filters=demo_conditions,
		fields=["utm_source", "utm_medium", "utm_campaign"],
		limit_page_length=0,
	):
		bucket(row)["demos"] += 1

	out = []
	for entry in grouped.values():
		signups = entry["signups"]
		entry["verification_rate"] = flt(entry["verified"] * 100.0 / signups, 2) if signups else 0.0
		entry["conversion_rate"] = flt(entry["paid"] * 100.0 / signups, 2) if signups else 0.0
		entry["value"] = flt(entry["value"], 2)
		out.append(entry)
	out.sort(key=lambda r: (r["signups"] + r["demos"]), reverse=True)
	return out
