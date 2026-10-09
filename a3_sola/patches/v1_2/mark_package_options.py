# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Mark the priced options that were built from their estimate's own package.

Only those are rebuilt from the package on save; an option added on the desk - of another
package, or priced by make - is left as it is. An option of the estimate's own package
with no make of its own is the package's, however it got there.
"""

import frappe


def execute():
	frappe.reload_doc("solar_crm", "doctype", "design_estimate_option")
	frappe.db.sql(
		"""update `tabDesign Estimate Option` opt
		join `tabSolar Design Estimate` est on est.name = opt.parent
		set opt.from_package = 1
		where opt.parenttype = 'Solar Design Estimate'
			and ifnull(opt.component_make, '') = ''
			and ifnull(est.solar_package, '') != ''
			and opt.solar_package = est.solar_package"""
	)
