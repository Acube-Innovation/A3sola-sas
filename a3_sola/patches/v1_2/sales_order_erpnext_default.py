# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Sales Order is ERPNext's own form: the solar, KYC and task fields come off it.

It stays linked to its quotation by ERPNext's item rows (prevdoc_docname); the handoff
finds the consumer from there, and the installation keeps its own link to the order.
"""

import frappe

FIELDS = (
	"a3s_solar_sb", "solar_consumer", "solar_installation",
	"a3s_kyc_sb", "kyc_status", "kyc_html",
	"a3s_task_sb", "assigned_by", "assigned_to", "assigned_on", "a3s_task_cb", "task_due_date", "task_cost",
)


def execute():
	for name in frappe.get_all("Custom Field", filters={"dt": "Sales Order", "fieldname": ["in", FIELDS]}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	frappe.clear_cache(doctype="Sales Order")
