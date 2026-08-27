# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Rebuild project costs when a contributing document is submitted.

Costs are re-derived, so this simply asks for a rebuild rather than adding anything.
"""

import frappe

from a3_sola.api import costing


def refresh(doc, method=None):
	project = doc.get("project")
	if not project and doc.get("solar_installation"):
		project = frappe.db.get_value("Solar Installation", doc.solar_installation, "project")
	if not project:
		return
	try:
		costing.recalculate_project_costs(project)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: cost refresh from {doc.doctype} {doc.name}")
