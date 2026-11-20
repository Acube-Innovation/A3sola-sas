# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Packages offer no Optional Add-ons: the section is hidden on the package, and an add-on
is entered on the estimate when it is wanted. The rows packages were given by default -
an extra panel, the inverter warranty extension - are cleared, so new estimates are not
filled with them. Estimates made already keep theirs."""

import frappe


def execute():
	frappe.db.delete("Solar Package Add-on", {"parenttype": "Solar Package"})
	frappe.clear_cache(doctype="Solar Package")
