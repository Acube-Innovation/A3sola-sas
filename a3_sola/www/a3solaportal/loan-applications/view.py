# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one loan application: the shared record page, with Print - the bank's
covering letter and feasibility report, as one PDF (api/loan_print.py), signed and sealed
or without, to sign by hand."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("loan-applications", name) if name else "/a3solaportal/loan-applications")
	detail_context(context, "loan-applications", name)
	context.print_route = "/api/method/a3_sola.api.loan_print.pdf?name=" + frappe.utils.quote(context.record.name)
	context.head_actions_template = "templates/includes/portal_loan_print.html"
	return context
