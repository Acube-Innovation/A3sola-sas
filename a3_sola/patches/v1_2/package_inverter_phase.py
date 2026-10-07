# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every package inverter row states the connection it is for: until now, the package's own.

Written directly, so packages are not re-priced or re-checked by the migration.
"""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package_inverter")
	frappe.db.sql(
		"""update `tabSolar Package Inverter` inverter
		join `tabSolar Package` package on package.name = inverter.parent
		set inverter.inverter_phase = package.connection_type
		where inverter.parenttype = 'Solar Package'
			and ifnull(inverter.inverter_phase, '') = ''
			and ifnull(package.connection_type, '') != ''"""
	)
