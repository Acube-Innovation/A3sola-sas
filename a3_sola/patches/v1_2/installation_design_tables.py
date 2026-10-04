# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The installation's System tab carries the Design Estimate's system tables.

Existing jobs are submitted, so the rows are inserted directly. Their summary fields are
left as they are: the serial register and issued documents already count against them.
"""

import frappe

from a3_sola.solar_operations.doctype.solar_installation.solar_installation import ESTIMATE_TABLES


def execute():
	frappe.reload_doc("solar_operations", "doctype", "solar_installation")
	for name in frappe.get_all(
		"Solar Installation", filters={"solar_design_estimate": ["is", "set"]}, pluck="name"
	):
		doc = frappe.get_doc("Solar Installation", name)
		if any(doc.get(table) for table in ESTIMATE_TABLES):
			continue
		estimate = frappe.get_doc("Solar Design Estimate", doc.solar_design_estimate)
		for table in ESTIMATE_TABLES:
			for row in estimate.get(table):
				doc.append(table, row.as_dict(no_default_fields=True)).db_insert()
