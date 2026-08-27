# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sales Invoice: keep the billing plan in step."""

import frappe

from a3_sola.api import billing, costing


def on_submit(doc, method=None):
	_refresh_plan(doc)
	_refresh_costs(doc)


def on_cancel(doc, method=None):
	_refresh_plan(doc)


def _refresh_plan(doc):
	if not doc.get("solar_billing_plan"):
		return
	plan = frappe.get_doc("Solar Billing Plan", doc.solar_billing_plan)
	billing.recompute_summary(plan)
	plan.flags.ignore_validate_update_after_submit = True
	plan.save(ignore_permissions=True)
	_roll_to_project(plan)


def _roll_to_project(plan):
	frappe.db.set_value(
		"Project",
		plan.project,
		{
			"total_billed_amount": plan.total_invoiced,
			"total_collected_amount": plan.total_collected,
			"outstanding_amount": plan.total_outstanding,
		},
		update_modified=False,
	)


def _refresh_costs(doc):
	"""Margin is measured against billed revenue, so it moves when an invoice does."""
	if not doc.get("project"):
		return
	try:
		costing.recalculate_project_costs(doc.project)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: cost refresh from {doc.name}")
