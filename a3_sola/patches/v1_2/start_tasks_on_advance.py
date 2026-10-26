# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's first advance starts Form 1, the stamp paper, the design freeze and the
structure material (api/stages.start_on_advance). The shared template takes a named person per
task (Assign to), Form 1 Payment's due date follows Form 1, and the structure material goes to
the job's Project Manager. Projects already past their advance are left as they are.
"""

import frappe

from a3_sola.setup import install_ops


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_template_detail")
	install_ops.setup()  # Form 1 Payment's anchor (a synced field)
	name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if not name:
		return
	# The default position is seeded once; the template's own row is changed here.
	frappe.db.set_value("Installation Stage Template Detail", {"parent": name, "stage_code": "SPROC"},
		"default_assignee", "Project Manager", update_modified=False)
	frappe.clear_document_cache("Installation Stage Template", name)
