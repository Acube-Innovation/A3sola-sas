# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Payment Entry: collections move the billing plan and the project."""

import frappe

from a3_sola.overrides.sales_invoice import _refresh_plan


def on_submit(doc, method=None):
	seen = set()
	for row in doc.get("references") or []:
		if row.reference_doctype != "Sales Invoice" or row.reference_name in seen:
			continue
		seen.add(row.reference_name)
		plan = frappe.db.get_value("Sales Invoice", row.reference_name, "solar_billing_plan")
		if plan:
			_refresh_plan(frappe._dict({"solar_billing_plan": plan}))
