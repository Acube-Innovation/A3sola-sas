# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An installation expense row's new Rate, Quantity and Source: each table's first row is the
installation line the system fills in (source "installation"), and a row with an Amount but no
Rate gets the Amount as its Rate, Quantity 1 - no amount changes; the next save sets the line's
Rate and Quantity from its roof type. Packages and design estimates alike; written straight."""

import frappe


def execute():
	frappe.db.sql("""update `tabDesign Estimate Installation Expense` set rate = amount, qty = 1
		where ifnull(rate, 0) = 0 and ifnull(amount, 0) != 0""")
	frappe.db.sql("""update `tabDesign Estimate Installation Expense` set qty = 1 where qty is null""")
	for parent, parenttype in frappe.db.sql("""select distinct parent, parenttype from `tabDesign Estimate Installation Expense`
			where parentfield = 'installation_expenses'"""):
		rows = frappe.get_all("Design Estimate Installation Expense", filters={"parent": parent, "parenttype": parenttype,
			"parentfield": "installation_expenses"}, fields=["name", "source"], order_by="idx asc")
		if rows and not any(r.source for r in rows):
			frappe.db.set_value("Design Estimate Installation Expense", rows[0].name, "source", "installation", update_modified=False)
