# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package add-on's new Rate, Quantity and Item Group: a row with an Amount but no Rate gets the
Amount as its Rate, Quantity 1 - no amount changes - and a row naming an Item takes its group."""

import frappe


def execute():
	frappe.db.sql("""update `tabSolar Package Add-on` set rate = amount, qty = 1
		where ifnull(rate, 0) = 0 and ifnull(amount, 0) != 0""")
	frappe.db.sql("""update `tabSolar Package Add-on` set qty = 1 where qty is null""")
	frappe.db.sql("""update `tabSolar Package Add-on` a join `tabItem` i on i.name = a.item_code
		set a.item_group = i.item_group where ifnull(a.item_group, '') = ''""")
