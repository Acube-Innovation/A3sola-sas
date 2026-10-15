# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one reimbursement: the shared record page, with the step that is due in
its head - Approve or Reject for an operations manager while it waits, Mark paid for
Accounts once approved - and a way back to its project."""

import frappe

from a3_sola.solar_operations.doctype.expense_reimbursement.expense_reimbursement import ACCOUNTS_ROLES
from a3_sola.api.stages import MANAGER_ROLES
from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("reimbursements", name) if name else "/a3solaportal/reimbursements")
	detail_context(context, "reimbursements", name)
	doc = context.record
	roles = set(frappe.get_roles())
	context.can_decide = doc.status == "Pending Approval" and bool(roles & set(MANAGER_ROLES))
	context.can_pay = doc.status == "Approved" and bool(roles & set(ACCOUNTS_ROLES))
	context.head_actions_template = "templates/includes/portal_reimbursement_actions.html"
	# Decided claims are fixed; only a waiting one is edited, by whoever may write it.
	context.can_write = context.can_write and doc.status == "Pending Approval"
	if doc.solar_installation:
		context.back_link = {"href": record_route("projects", doc.solar_installation), "label": "Back to project"}
	return context
