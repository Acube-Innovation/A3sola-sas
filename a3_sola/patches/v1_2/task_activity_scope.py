# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every template task carries an activity scope now, and the field is mandatory.

The shared template's rows predate it, so the seed fills each one from its task code.
"""

import frappe

from a3_sola.setup import install_ops


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_template_detail")
	if frappe.db.exists("Installation Stage Template", {"is_shared": 1}):
		install_ops.seed_stage_templates()
