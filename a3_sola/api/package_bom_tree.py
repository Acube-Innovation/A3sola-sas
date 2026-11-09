# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package's BOM tab as a full BOM: every part of the package in one of its three boxes,
each ERPNext Product Bundle or BOM opened out into the items it is made of.

On every save of the package:

1. The rows of its other tabs are copied into the BOM tab - the goods into the Material BOM (the
   default solar panel, each inverter option - needed with that inverter only - and the optional
   add-ons), the services into the Expenses (the KSEB and the installation rows). A copied row
   says where it is from (`source_row`) and is changed there, not here; the rows typed or
   uploaded into the BOM tab stay as they are.
2. A row whose Item is a Product Bundle, or has a BOM, is the parent of its items: they follow
   it as Component rows, their quantities for the parent's, needed with what the parent is.

The copies and the components are worked out again on each save. They are for reading the
package whole: an estimate takes only the rows typed into the BOM tab
(solar_design_estimate.package_bom_rows), the package's own BOM counts each part once
(package_bom_tables.bom_lines) and a bundle's parts, not the bundle, go into it.
"""

import frappe
from frappe.utils import cint, flt

#: Where each tab's rows go, and how a row reads: (tab table, BOM-tab table, tab label, item
#: field, quantity field, rate field).
SOURCES = (
	("modules", "material_bom", "Solar Panel", "module_item", "module_count", "rate"),
	("inverters", "material_bom", "Inverter", "inverter_item", "inverter_count", "unit_rate"),
	("optional_add_ons", "material_bom", "Optional Add-ons", "item_code", None, "amount"),
	("kseb_expenses", "expenses", "KSEB", "particulars", None, "amount"),
	("installation_expenses", "expenses", "Installation", "item", None, "amount"),
)
TABLES = ("material_bom", "structure_boms", "expenses")
#: What a row is needed with, which its components are needed with too.
DEPENDS = {"material_bom": ("inverters",), "structure_boms": ("roof_types", "panel_capacities"), "expenses": ()}
BUNDLE, BOM, COMPONENT = "Bundle", "BOM", "Component"
#: Kept off a row copied to be set again.
META = ("parent", "parenttype", "parentfield", "idx", "creation", "modified", "owner", "modified_by", "docstatus")


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
def _default(rows):
	return next((r for r in rows if r.get("is_default")), rows[0] if rows else None)


def _copies(doc):
	"""The other tabs' rows as BOM-tab rows, per BOM-tab table."""
	out = {t: [] for t in TABLES}
	for table, target, label, item_field, qty_field, rate_field in SOURCES:
		rows = [r for r in doc.get(table) or [] if r.get(item_field)]
		if table == "modules":
			rows = [r for r in [_default(rows)] if r]
		for row in rows:
			item = row.get(item_field)
			qty = (cint(row.get(qty_field)) if qty_field else 0) or 1
			rate = flt(row.get(rate_field))
			if table == "inverters" and not rate and flt(row.get("cost")):
				rate = flt(row.get("cost")) / qty
			copy = {"item": item, "qty": qty, "rate": rate, "source_row": f"{label} row {row.idx}"}
			if target == "material_bom":
				# An inverter option's row is needed with that inverter only; the rest with every one.
				copy["inverters"] = item if table == "inverters" else ""
			out[target].append(copy)
	return out


def _own(row):
	"""A row typed or uploaded into the BOM tab, as it stands."""
	data = row.as_dict() if hasattr(row, "as_dict") else dict(row)
	for key in META:
		data.pop(key, None)
	return data


def _item_details(item, cache):
	if item not in cache:
		cache[item] = frappe.db.get_value("Item", item, ["item_group", "stock_uom", "valuation_rate"], as_dict=True) or {}
	return cache[item]


def sync(doc):
	"""The BOM tab's three tables made whole again: the other tabs' rows copied in, the rows typed
	into it kept, and each bundle or BOM row followed by its items."""
	copies, made, details = _copies(doc), {}, {}
	for table in TABLES:
		own = [_own(r) for r in doc.get(table) or [] if not r.get("source_row") and r.get("row_kind") != COMPONENT]
		rows = []
		for row in copies[table] + own:
			item = row.get("item")
			info = _item_details(item, details) if item else {}
			if not row.get("category"):
				row["category"] = info.get("item_group")
			if not row.get("uom"):
				row["uom"] = info.get("stock_uom")
			row["amount"] = flt(row.get("qty")) * flt(row.get("rate"))
			kind, bom, parts = made_of(item, made) if item else (None, None, [])
			row["row_kind"], row["bom_no"] = kind or "", bom
			rows.append(row)
			for code, per, uom, rate in parts:
				qty = per * flt(row.get("qty"))
				if qty <= 0:
					continue
				part = _item_details(code, details)
				child = {"item": code, "category": part.get("item_group"), "uom": uom or part.get("stock_uom"),
					"qty": qty, "rate": rate or flt(part.get("valuation_rate")), "row_kind": COMPONENT,
					"source_row": row.get("source_row") or ""}
				child["amount"] = child["qty"] * child["rate"]
				for field in DEPENDS[table]:
					child[field] = row.get(field)
				rows.append(child)
		doc.set(table, rows)


def is_own(row):
	"""Whether a BOM-tab row is one typed or uploaded there - not a copy, not a component."""
	return not row.get("source_row") and row.get("row_kind") != COMPONENT
