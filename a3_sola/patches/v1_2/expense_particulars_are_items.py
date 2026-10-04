# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEB expense particulars and installation items link to Items now.

The KSEB rows the system fills in carried text such as "Registration Fee - 5.0 kW"; they are
pointed at their seeded Item by source. The installation row's text already is its Item's code. Hand-typed rows are left alone: they cannot be
matched to an Item, and the next save of their document will say so.
"""

import frappe

from a3_sola.api.expenses import EXPENSE_ITEMS
from a3_sola.setup.install import seed_expense_items


def execute():
	frappe.reload_doc("solar_crm", "doctype", "design_estimate_kseb_expense")
	seed_expense_items()

	for source, code in EXPENSE_ITEMS["kseb_expenses"].items():
		frappe.db.sql(
			"update `tabDesign Estimate KSEB Expense` set particulars = %s where source = %s",
			(code, source),
		)
