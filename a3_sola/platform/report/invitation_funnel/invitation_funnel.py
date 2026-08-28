# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Invitation Funnel.

Sent, accepted, expired - per tenant. A tenant whose invitations all expire is a
tenant whose team never arrived, which is a renewal conversation waiting to happen."""

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 130},
		{"label": _("Organisation"), "fieldname": "tenant_name", "fieldtype": "Data", "width": 200},
		{"label": _("Sent"), "fieldname": "sent", "fieldtype": "Int", "width": 80},
		{"label": _("Accepted"), "fieldname": "accepted", "fieldtype": "Int", "width": 100},
		{"label": _("Open"), "fieldname": "open", "fieldtype": "Int", "width": 80},
		{"label": _("Expired"), "fieldname": "expired", "fieldtype": "Int", "width": 90},
		{"label": _("Revoked"), "fieldname": "revoked", "fieldtype": "Int", "width": 90},
		{"label": _("Failed"), "fieldname": "failed", "fieldtype": "Int", "width": 90},
		{"label": _("Acceptance"), "fieldname": "acceptance", "fieldtype": "Percent", "width": 120},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Tenant Invitation", fields=["tenant", "status"], limit_page_length=0
	)
	buckets = {}
	for row in rows:
		bucket = buckets.setdefault(
			row.tenant,
			{"tenant": row.tenant, "sent": 0, "accepted": 0, "open": 0, "expired": 0,
			 "revoked": 0, "failed": 0},
		)
		bucket["sent"] += 1
		if row.status == "Accepted":
			bucket["accepted"] += 1
		elif row.status in ("Pending", "Sent"):
			bucket["open"] += 1
		elif row.status == "Expired":
			bucket["expired"] += 1
		elif row.status == "Revoked":
			bucket["revoked"] += 1
		elif row.status == "Failed":
			bucket["failed"] += 1

	out = []
	for tenant, bucket in buckets.items():
		bucket["tenant_name"] = frappe.db.get_value("Tenant", tenant, "tenant_name")
		bucket["acceptance"] = round(bucket["accepted"] * 100.0 / (bucket["sent"] or 1), 1)
		out.append(bucket)
	return sorted(out, key=lambda r: r["acceptance"])
