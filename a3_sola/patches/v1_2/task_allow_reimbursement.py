# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Claim Reimbursement only on the tasks the template ticks (Allow Reimbursement). Existing
templates tick the stamp paper - the one task already claimed for; the rest are the
business's to tick."""

import frappe

from a3_sola.setup.install_ops import REIMBURSABLE


def execute():
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_template_detail")
	frappe.db.sql(
		"""update `tabInstallation Stage Template Detail` set allow_reimbursement = 1
		where stage_code in %s""",
		(REIMBURSABLE,),
	)
