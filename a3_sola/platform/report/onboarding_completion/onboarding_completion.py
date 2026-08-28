# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Onboarding Completion.

Setup progress per tenant, with the incomplete critical items named. The account
mapping one matters most: until it is done nothing the tenant invoices reaches a
ledger, and they will not find that out until their accountant asks."""

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
		{"label": _("Done"), "fieldname": "completed", "fieldtype": "Data", "width": 90},
		{"label": _("Progress"), "fieldname": "percent", "fieldtype": "Percent", "width": 110},
		{"label": _("Account Mapping"), "fieldname": "account_mapping", "fieldtype": "Data", "width": 150},
		{"label": _("Outstanding Critical"), "fieldname": "outstanding", "fieldtype": "Data", "width": 420},
	]


def get_data(filters):
	rows = frappe.get_all(
		"Tenant", filters={"status": ["in", ["Active", "Provisioned with Errors"]]},
		fields=["name", "tenant_name"], limit_page_length=0,
	)
	out = []
	for row in rows:
		tasks = frappe.get_all(
			"Tenant Onboarding Task",
			filters={"parent": row.name, "parenttype": "Tenant"},
			fields=["task_code", "task_title", "is_critical", "is_complete"],
		)
		if not tasks:
			continue
		done = [t for t in tasks if cint(t.is_complete)]
		outstanding = [t for t in tasks if cint(t.is_critical) and not cint(t.is_complete)]
		mapping = next((t for t in tasks if t.task_code == "ACCOUNT_MAPPING"), None)
		out.append(
			{
				**row,
				"completed": f"{len(done)} / {len(tasks)}",
				"percent": round(len(done) * 100.0 / len(tasks), 1),
				"account_mapping": (
					_("Done") if mapping and cint(mapping.is_complete) else _("NOT MAPPED")
				),
				"outstanding": ", ".join(t.task_title for t in outstanding),
			}
		)
	return sorted(out, key=lambda r: r["percent"])
