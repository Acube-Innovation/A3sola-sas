# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The tenant admin's own seats page. Login required, tenant derived from the session."""

import frappe

from a3_sola.api import invitations

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in to manage your team."), frappe.PermissionError)

	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Team and Seats"
	try:
		context.seats = invitations.my_seats()
	except frappe.PermissionError:
		context.seats = None
	return context
