# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A KSEB expense row's new Rate and Quantity, so its Amount reads as Rate x Quantity: a row with an
Amount but no Rate - blank, or the 0 the new column starts every row at - gets its Amount as the
Rate and Quantity 1, so no amount changes. Packages and design estimates alike (the table is
shared); written straight to the rows."""

import frappe


def execute():
	frappe.db.sql("""update `tabDesign Estimate KSEB Expense` set rate = amount, qty = 1
		where ifnull(rate, 0) = 0 and ifnull(amount, 0) != 0""")
	frappe.db.sql("""update `tabDesign Estimate KSEB Expense` set qty = 1 where qty is null""")
