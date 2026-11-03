# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every Solar Package made of Items, its BOMs cleared for making by hand, and Draft.

1. Each package is the finished good: its Item is coded by the package's code and named by
   its name, in Solar Packages.
2. Each specification row - panel, inverter, battery, balance of system, KSEB, mounting,
   installation, add-on - is linked to an Item of its category, made from the row's text
   where none exists. The text is kept: the package's prices are keyed by it.
3. Every BOM is cancelled and deleted, and cleared from wherever it was named (packages,
   Settings, projects, tasks), so the package BOMs can be made afresh.
4. The Item list is left to the packages' Items: an Item nothing names is deleted; one a
   transaction names (a supplier bill, a quotation) is disabled instead.
5. Every package is set to Draft, to be checked and set Active.
"""

import frappe

from a3_sola.api import package_items as pi
from a3_sola.api.expenses import EXPENSE_ITEMS


def execute():
	packages = frappe.get_all("Solar Package", pluck="name")
	pi.ensure_group(pi.PACKAGE_GROUP)
	pi.ensure_group(pi.ADD_ON_GROUP)
	for name in packages:
		package = frappe.get_doc("Solar Package", name)
		finished_good(package)
		link_rows(package)
	remove_boms()
	keep = package_item_codes() | {code for items in EXPENSE_ITEMS.values() for code in items.values()}
	clear_items(keep)
	frappe.db.sql("update `tabSolar Package` set status = 'Draft'")


def finished_good(package):
	code = (package.specification_code or package.package_name or "").strip()[:140]
	if not code:
		return
	if package.item and frappe.db.exists("Item", package.item):
		frappe.db.set_value("Item", package.item, {"item_name": (package.package_name or code)[:140],
			"item_group": pi.PACKAGE_GROUP, "disabled": 0}, update_modified=False)
		return
	if not frappe.db.exists("Item", code):
		item = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": (package.package_name or code)[:140],
			"description": package.package_name, "item_group": pi.PACKAGE_GROUP, "stock_uom": "Nos",
			"is_stock_item": 0, "is_sales_item": 1, "is_purchase_item": 0})
		if item.meta.has_field("gst_hsn_code") and frappe.db.exists("GST HSN Code", "85414300"):
			item.gst_hsn_code = "85414300"
		item.insert(ignore_permissions=True)
	frappe.db.set_value("Solar Package", package.name, "item", code, update_modified=False)


def link_rows(package):
	for table, (field, text_field) in pi.ROWS.items():
		for row in package.get(table) or []:
			if row.get(field) and frappe.db.exists("Item", row.get(field)):
				continue
			text = row.get(text_field) if text_field else None
			if not text:
				continue
			group = pi.leaf_group(table, row, package)
			pi.ensure_group(group, "Modules" if group.endswith("Modules") else "Inverters" if group.endswith("Inverters")
				else "All Item Groups")
			item = pi.item_for(text, group, pi.hsn_for(table, row, group), pi.category(table, row),
				name=pi.item_name_for(table, row, text))
			if item:
				frappe.db.set_value(row.doctype, row.name, field, item, update_modified=False)


def package_item_codes():
	codes = set(frappe.get_all("Solar Package", filters={"item": ["is", "set"]}, pluck="item"))
	for table, (field, _text) in pi.ROWS.items():
		doctype = frappe.get_meta("Solar Package").get_field(table).options
		codes |= set(frappe.get_all(doctype, filters={"parenttype": "Solar Package", field: ["is", "set"]}, pluck=field))
	return codes


def remove_boms():
	boms = frappe.get_all("BOM", pluck="name")
	if not boms:
		return
	frappe.db.sql("update `tabSolar Package` set bom = null")
	for doctype in ("Solar Package Structure BOM", "Inverter Capacity BOM", "Panel Capacity Structure BOM"):
		frappe.db.delete(doctype, {"bom": ["in", boms]})
	names = tuple(boms)
	for field in ("structure_bom", "material_bom"):
		frappe.db.sql(f"update `tabSolar Installation` set `{field}` = null where `{field}` in %s", [names])
	for field in ("bom", "structure_bom", "material_bom"):
		frappe.db.sql(f"update `tabInstallation Task` set `{field}` = null where `{field}` in %s", [names])
	frappe.db.sql("update `tabItem` set default_bom = null where default_bom in %s", [names])
	# Every BOM goes, so one naming another as a sub-assembly is no obstacle: removed outright
	# rather than cancelled one by one in dependency order.
	for child in ("BOM Item", "BOM Explosion Item", "BOM Operation", "BOM Scrap Item", "BOM Website Item",
			"BOM Website Operation"):
		if frappe.db.table_exists(child):
			frappe.db.delete(child, {"parenttype": "BOM", "parent": ["in", boms]})
	frappe.db.delete("BOM", {"name": ["in", boms]})
	frappe.clear_cache(doctype="A3 Sola Settings")


#: Records that belong to an Item and go with it - not uses of it.
OWN = {"Item Default", "Item Price", "Item Barcode", "Item Tax", "Item Reorder", "Item Supplier",
	"Item Customer Detail", "Item Variant Attribute", "UOM Conversion Detail", "Item Website Specification", "Bin"}


def _used():
	links = frappe.db.sql("""select parent, fieldname from tabDocField where fieldtype = 'Link' and options = 'Item'
		union select dt, fieldname from `tabCustom Field` where fieldtype = 'Link' and options = 'Item'""")
	used = set()
	for doctype, field in links:
		if doctype in OWN or doctype == "Item" or not frappe.db.table_exists(doctype) or frappe.get_meta(doctype).issingle:
			continue
		used |= {code for (code,) in frappe.db.sql(f"select distinct `{field}` from `tab{doctype}` where ifnull(`{field}`, '') != ''")}
	return used


def clear_items(keep):
	used = _used()
	for name in frappe.get_all("Item", pluck="name"):
		if name in keep:
			continue
		if name in used:
			frappe.db.set_value("Item", name, "disabled", 1, update_modified=False)
			continue
		frappe.db.savepoint("item_delete")
		try:
			frappe.delete_doc("Item", name, ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point="item_delete")
			frappe.db.set_value("Item", name, "disabled", 1, update_modified=False)
