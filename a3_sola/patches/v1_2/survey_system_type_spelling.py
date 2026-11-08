# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A survey's Type of System is spelled as the design estimate spells it (On-Grid, Off-Grid),
so the estimate can start from it."""

import frappe


def execute():
	for old, new in (("On-grid", "On-Grid"), ("Off-grid", "Off-Grid")):
		frappe.db.sql("update `tabSite Survey` set system_type = %s where system_type = %s", (new, old))
