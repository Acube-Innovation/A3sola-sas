# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""DCR Compliant on design estimates is their package's.

It was fetched before the estimate took its option row's package, so an estimate made on a
subsidy (DCR) package could say No. Draft and submitted estimates are set from their package.
"""

import frappe


def execute():
	frappe.db.sql(
		"""update `tabSolar Design Estimate` e join `tabSolar Package` p on p.name = e.solar_package
		set e.is_dcr_compliant = ifnull(p.is_dcr_compliant, 0)
		where e.docstatus < 2 and ifnull(e.is_dcr_compliant, 0) != ifnull(p.is_dcr_compliant, 0)"""
	)
