# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Controller for the customer portal page.

Login is required and ownership is derived from the session on every request. Nothing here
takes a customer, an installation or a project from the URL.
"""

import frappe

from a3_sola.api import portal

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in to view your solar system."), frappe.PermissionError)

	context.no_cache = 1
	context.systems = portal.systems()
	context.ticket_categories = frappe.get_meta("Service Ticket").get_field("category").options.split("\n")

	for system in context.systems:
		system["generation"] = portal.generation_history(system["name"])
		system["service"] = portal.service_history(system["name"])
		system["documents"] = portal.documents(system["name"])
		system["invoices"] = portal.invoices(system["name"])
	return context
