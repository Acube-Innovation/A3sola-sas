# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a Solar Package's Items are made of: an ERPNext Product Bundle's items, or an Item's BOM.

A bundle or an Item with a BOM may stand in any row of a package (package_items). Its parts go
into the package's own ERPNext BOM - a bundle as its items, which a BOM cannot hold as one; an
Item with a BOM as a sub-assembly (line_items, package_items.bom_lines, package_bom_tables.bom_lines).

The BOM tab holds only the rows typed or uploaded into it. Nothing is copied there from the other
tabs on save, and no bundle or BOM is opened out into rows under it: rows a save once added that
way are taken out on the next save (keep_own_rows).
"""

import frappe
from frappe.utils import flt

TABLES = ("material_bom", "structure_boms", "expenses")
BUNDLE, BOM, COMPONENT = "Bundle", "BOM", "Component"
#: Set on rows by the save that once filled the BOM tab; cleared now.
TREE_FIELDS = ("row_kind", "bom_no", "source_row")


# ------------------------------------------------------------------ what an Item is made of
def bundle_of(item):
	"""The Product Bundle an Item is, if it is one."""
	if not item or not frappe.db.exists("DocType", "Product Bundle"):
		return None
	filters = {"new_item_code": item}
	if frappe.get_meta("Product Bundle").has_field("disabled"):
		filters["disabled"] = 0
	return frappe.db.get_value("Product Bundle", filters)


def bom_of(item):
	"""The Item's own BOM: its default, else its newest active one."""
	if not item:
		return None
	default = frappe.db.get_value("Item", item, "default_bom")
	if default and frappe.db.get_value("BOM", default, ["is_active", "docstatus"]) == (1, 1):
		return default
	return frappe.db.get_value("BOM", {"item": item, "is_active": 1, "docstatus": 1}, "name",
		order_by="is_default desc, creation desc")


def made_of(item, cache=None):
	"""(kind, BOM, parts): a bundle's or a BOM's items, each (item, quantity for one, UOM, rate);
	(None, None, []) for an Item that is neither."""
	cache = {} if cache is None else cache
	if item in cache:
		return cache[item]
	out = (None, None, [])
	bundle = bundle_of(item)
	if bundle:
		parts = frappe.get_all("Product Bundle Item", filters={"parent": bundle, "parenttype": "Product Bundle"},
			fields=["item_code", "qty", "uom", "rate"], order_by="idx")
		out = (BUNDLE, None, [(p.item_code, flt(p.qty), p.uom, flt(p.rate)) for p in parts])
	else:
		bom = bom_of(item)
		if bom:
			per = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
			parts = frappe.get_all("BOM Item", filters={"parent": bom, "parenttype": "BOM"},
				fields=["item_code", "qty", "uom", "rate"], order_by="idx")
			out = (BOM, bom, [(p.item_code, flt(p.qty) / per, p.uom, flt(p.rate)) for p in parts])
	cache[item] = out
	return out


def is_assembly(item):
	"""Whether the Item is a Product Bundle or has a BOM - a part made of other parts."""
	return bool(made_of(item)[0])


def line_items(item, qty, cache=None):
	"""What goes into the package's own BOM for `qty` of an Item: a bundle's parts (ERPNext's
	bundles are for selling only, so a BOM cannot hold one), else the Item - one with a BOM of its
	own is a sub-assembly, its BOM named on the line by ERPNext."""
	kind, _bom, parts = made_of(item, cache)
	if kind == BUNDLE and parts:
		return [(code, per * qty) for code, per, _uom, _rate in parts if per > 0]
	return [(item, qty)]


# ------------------------------------------------------------------ on save
def keep_own_rows(doc):
	"""The BOM tab's three tables as typed: a row once copied from another tab, or listed under a
	bundle or BOM as one of its items, is taken out; the rest keep their place."""
	for table in TABLES:
		rows = [r for r in doc.get(table) or [] if is_own(r)]
		for row in rows:
			for field in TREE_FIELDS:
				row.set(field, None)
		doc.set(table, rows)


def is_own(row):
	"""Whether a BOM-tab row is one typed or uploaded there - not a copy, not a component."""
	return not row.get("source_row") and row.get("row_kind") != COMPONENT
