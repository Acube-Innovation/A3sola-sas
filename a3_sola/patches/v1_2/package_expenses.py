# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Cost tab's Package Cost by Inverter gives way to Expenses (Solar Package Expense).

What the price rows held that is not worked out now moves onto the inverter options: the panel
an inverter was priced on, where it is not the package's default panel, becomes its Built
with Panel; an MRP whose inverter option has no Cost becomes its Cost. The subsidy, net cost,
statutory fees and generation band are worked out (solar_package.price_for). The price rows
themselves are left in the database, unread.
"""

import frappe
from frappe.utils import flt


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package_inverter")
	frappe.reload_doc("solar_crm", "doctype", "solar_package_expense")
	frappe.reload_doc("solar_crm", "doctype", "solar_package")
	if not frappe.db.table_exists("Solar Package Price"):
		return

	modules = {}
	for m in frappe.get_all("Solar Package Module", filters={"parenttype": "Solar Package"},
			fields=["parent", "module_specification", "is_default"], order_by="parent, is_default desc, idx"):
		modules.setdefault(m.parent, []).append(m)
	inverters = {}
	for r in frappe.get_all("Solar Package Inverter", filters={"parenttype": "Solar Package"},
			fields=["name", "parent", "inverter_specification", "cost", "panel_specification"]):
		inverters.setdefault((r.parent, r.inverter_specification), r)

	for price in frappe.get_all("Solar Package Price", filters={"parenttype": "Solar Package"},
			fields=["parent", "module", "inverter", "system_cost"], order_by="parent, idx"):
		row = inverters.get((price.parent, price.inverter))
		if not row:
			continue
		values = {}
		offered = modules.get(price.parent) or []
		default = offered[0].module_specification if offered else None
		if price.module and price.module != default and price.module in {m.module_specification for m in offered} \
				and not row.panel_specification:
			values["panel_specification"] = row.panel_specification = price.module
		if not flt(row.cost) and flt(price.system_cost):
			values["cost"] = row.cost = flt(price.system_cost)
		if values:
			frappe.db.set_value("Solar Package Inverter", row.name, values, update_modified=False)

	for name in frappe.get_all("Solar Package", pluck="name"):
		frappe.clear_document_cache("Solar Package", name)
