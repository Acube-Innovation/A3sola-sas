# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Isolation Test Status.

Last run and result per tenant, with anything never tested or failing at the top.
A tenant that has never been tested is indistinguishable from one that would fail."""

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
		{"label": _("Tenant Status"), "fieldname": "status", "fieldtype": "Data", "width": 160},
		{"label": _("Result"), "fieldname": "result", "fieldtype": "Data", "width": 140},
		{"label": _("Last Run"), "fieldname": "isolation_test_on", "fieldtype": "Datetime", "width": 170},
		{"label": _("Checks"), "fieldname": "checks", "fieldtype": "Int", "width": 90},
		{"label": _("Failures"), "fieldname": "failures", "fieldtype": "Int", "width": 100},
		{"label": _("First Failure"), "fieldname": "first_failure", "fieldtype": "Data", "width": 340},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Tenant",
		fields=["name", "tenant_name", "status", "isolation_test_passed", "isolation_test_on"],
		limit_page_length=0,
	)
	out = []
	for row in rows:
		results = frappe.get_all(
			"Tenant Isolation Test Result",
			filters={"parent": row.name, "parenttype": "Tenant"},
			fields=["test_code", "test_description", "status", "actual_result"],
		)
		failures = [r for r in results if r.status in ("Failed", "Error")]
		if not row.isolation_test_on:
			result, rank = _("Never tested"), 0
		elif failures:
			result, rank = _("FAILED"), 1
		else:
			result, rank = _("Passed"), 2
		out.append(
			{
				**row,
				"result": result,
				"checks": len(results),
				"failures": len(failures),
				"first_failure": (
					f"{failures[0].test_code}: {failures[0].actual_result}" if failures else ""
				),
				"_rank": rank,
			}
		)
	return sorted(out, key=lambda r: (r["_rank"], r["name"]))
