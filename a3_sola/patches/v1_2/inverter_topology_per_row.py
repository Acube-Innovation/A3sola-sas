# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Inverter Topology moves from the package onto each of its inverter options: every option
takes its package's topology, which then follows the default option (solar_package.py
topology_from_inverters)."""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package_inverter")
	frappe.reload_doc("solar_crm", "doctype", "solar_package")
	frappe.db.sql("""
		update `tabSolar Package Inverter` row
		join `tabSolar Package` pkg on pkg.name = row.parent
		set row.inverter_topology = coalesce(nullif(pkg.inverter_topology, ''), 'String')
		where row.parenttype = 'Solar Package' and coalesce(row.inverter_topology, '') = ''""")
