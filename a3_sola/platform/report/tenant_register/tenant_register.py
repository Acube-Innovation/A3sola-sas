# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Tenant Register.

Every customer workspace on one page: what they bought, how much of it they are using,
and whether their isolation has ever been verified. The one report to open when
somebody asks "how many customers do we have and are they all right"."""

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Tenant"), "fieldname": "name", "fieldtype": "Link", "options": "Tenant", "width": 130},
		{"label": _("Organisation"), "fieldname": "tenant_name", "fieldtype": "Data", "width": 200},
		{"label": _("Code"), "fieldname": "tenant_code", "fieldtype": "Data", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 90},
		{"label": _("Seats Used"), "fieldname": "seats_used", "fieldtype": "Data", "width": 100},
		{"label": _("Modules"), "fieldname": "modules", "fieldtype": "Data", "width": 220},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 180},
		{"label": _("Provisioned"), "fieldname": "provisioned_on", "fieldtype": "Datetime", "width": 160},
		{"label": _("Isolation"), "fieldname": "isolation", "fieldtype": "Data", "width": 130},
	]


def get_data(filters):
	conditions = {}
	if filters.get("status"):
		conditions["status"] = filters["status"]
	rows = frappe.get_all(
		"Tenant",
		filters=conditions,
		fields=["name", "tenant_name", "tenant_code", "status", "plan_code", "company",
		        "provisioned_on", "active_users", "user_quota", "isolation_test_passed",
		        "isolation_test_on"],
		order_by="creation desc",
		limit_page_length=0,
	)
	out = []
	for row in rows:
		modules = frappe.get_all(
			"Tenant Module", filters={"parent": row.name, "parenttype": "Tenant", "is_enabled": 1},
			pluck="module_name",
		)
		if not row.isolation_test_on:
			isolation = _("Never tested")
		elif cint(row.isolation_test_passed):
			isolation = _("Passed")
		else:
			isolation = _("FAILED")
		out.append(
			{
				**row,
				"seats_used": f"{cint(row.active_users)} / {cint(row.user_quota)}",
				"modules": ", ".join(modules) or _("none"),
				"isolation": isolation,
			}
		)
	return out
