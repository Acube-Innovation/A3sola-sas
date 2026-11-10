# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Product Bundle or an Item with a BOM chosen on a package's tab is replaced by its items,
each a row of its own, tagged with what it came from - Bundle or BOM (bundle_type), which one
(bundle_ref), how many of it (bundle_qty) and which adding of it (bundle_key) - so a print can
show them together again.

On the Solar Panel and Inverter tabs a kit is still one option: its first row carries the
option - its specification, make, default tick and the rest - and its other rows are its parts
(bundle_part), counted in the option's amount and never options themselves.

Each item is priced at its selling price: its Item Price in the Selling Settings' price list
(Standard Selling), 0 where it has none. Its quantity is its quantity in the bundle or BOM
times how many of the bundle the row was for.
"""

import json
import math

import frappe
from frappe.utils import cint, flt

#: Each tab whose rows a bundle or BOM opens into: its Item, quantity, rate and text fields.
TABLES = {
	"modules": {"item": "module_item", "qty": "module_count", "rate": "rate", "text": "module_specification"},
	"inverters": {"item": "inverter_item", "qty": "inverter_count", "rate": "unit_rate", "text": "inverter_specification"},
	"installation_expenses": {"item": "item", "qty": "qty", "rate": "rate", "text": "specification"},
	"material_bom": {"item": "item", "qty": "qty", "rate": "rate", "text": "description", "uom": "uom", "category": "category"},
	"structure_boms": {"item": "item", "qty": "qty", "rate": "rate", "text": "description", "uom": "uom", "category": "category"},
	"expenses": {"item": "item", "qty": "qty", "rate": "rate", "text": "description", "uom": "uom", "category": "category"},
}
#: The tabs whose rows are options: a kit's rows there are one option, its first row's.
OPTION_TABLES = ("modules", "inverters")
#: What a row from a bundle or BOM says of it.
KIT_FIELDS = ("bundle_type", "bundle_ref", "bundle_qty", "bundle_key", "bundle_part")
#: Not carried from the row chosen into the rows of its items.
NOT_CARRIED = {"name", "idx", "parent", "parentfield", "parenttype", "doctype", "creation", "modified", "owner",
	"modified_by", "docstatus", "amount", "__islocal", "__unsaved"}


def assembly(item):
	"""("Bundle", the Product Bundle) or ("BOM", its BOM) for an Item that is one; else None.
	A package's own Item, whose BOM is the package's, is not one."""
	from a3_sola.api.package_items import PACKAGE_GROUP

	if not item or frappe.db.get_value("Item", item, "item_group") == PACKAGE_GROUP:
		return None
	filters = {"new_item_code": item}
	if frappe.get_meta("Product Bundle").has_field("disabled"):
		filters["disabled"] = 0
	bundle = frappe.db.get_value("Product Bundle", filters, "name")
	if bundle:
		return "Bundle", bundle
	bom = frappe.db.get_value("Item", item, "default_bom")
	if not (bom and frappe.db.get_value("BOM", bom, "docstatus") == 1):
		bom = frappe.db.get_value("BOM", {"item": item, "is_active": 1, "docstatus": 1}, "name", order_by="is_default desc, creation desc")
	return ("BOM", bom) if bom else None


def parts(kind, ref):
	"""A bundle's or a BOM's items, in its order: [(item, quantity for one of it, UOM)]."""
	if kind == "Bundle":
		return [(r.item_code, flt(r.qty), r.uom) for r in frappe.get_all("Product Bundle Item",
			filters={"parent": ref, "parenttype": "Product Bundle"}, fields=["item_code", "qty", "uom"], order_by="idx asc")
			if r.item_code]
	made = flt(frappe.db.get_value("BOM", ref, "quantity")) or 1
	return [(r.item_code, flt(r.qty) / made, r.uom or r.stock_uom) for r in frappe.get_all("BOM Item",
		filters={"parent": ref, "parenttype": "BOM"}, fields=["item_code", "qty", "uom", "stock_uom"], order_by="idx asc")
		if r.item_code]


def selling_rate(item, uom=None):
	"""The Item's price in the Selling Settings' price list, in this UOM where it has one; else 0."""
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	prices = frappe.get_all("Item Price", filters={"item_code": item, "price_list": price_list},
		fields=["price_list_rate", "uom"], order_by="valid_from desc, modified desc")
	hit = next((p for p in prices if uom and p.uom == uom), None) or (prices[0] if prices else None)
	return flt(hit.price_list_rate) if hit else 0.0


def opens(table, row):
	"""Whether a row is to be replaced by its items: a bundle or BOM not yet opened."""
	spec = TABLES.get(table)
	return bool(spec and not row.get("bundle_ref") and assembly(row.get(spec["item"])))


def expand(table, row):
	"""The rows a row opens into, as dicts - [row] itself when it is no bundle or BOM.

	The first keeps everything the row said (on the panel and inverter tabs, the option); each
	row takes its item, its quantity, its selling price and, but for an option's first, its own
	description."""
	from a3_sola.api.package_bom_tables import item_text

	spec = TABLES[table]
	found = assembly(row.get(spec["item"])) if not row.get("bundle_ref") else None
	lines = parts(*found) if found else []
	if not lines:
		return [row]
	kind, ref = found
	count = flt(row.get(spec["qty"])) or 1
	whole = table in OPTION_TABLES
	key = frappe.generate_hash(length=10)
	out = []
	for i, (item, per, uom) in enumerate(lines):
		head = i == 0
		new = {k: v for k, v in dict(row).items() if k not in NOT_CARRIED} if (head or not whole) else {}
		qty = per * count
		new.update({spec["item"]: item, spec["qty"]: math.ceil(qty - 1e-9) if whole else qty, spec["rate"]: selling_rate(item, uom),
			"bundle_type": kind, "bundle_ref": ref, "bundle_qty": count, "bundle_key": key})
		# Its amount at once, as the save works it out (rate x quantity): the page shows it before then.
		new["amount"] = flt(new[spec["rate"]]) * flt(new[spec["qty"]])
		if not (whole and head):
			new[spec["text"]] = item_text(item)
		if whole:
			new["bundle_part"] = 0 if head else 1
			if not head:
				new["is_default"] = 0
				# A part is built as its option is (a required field).
				if row.get("inverter_topology"):
					new["inverter_topology"] = row.get("inverter_topology")
		if spec.get("uom"):
			new[spec["uom"]] = uom or frappe.db.get_value("Item", item, "stock_uom")
		if spec.get("category"):
			new[spec["category"]] = frappe.db.get_value("Item", item, "item_group")
		if table == "installation_expenses" and not head:
			new.pop("source", None)
		out.append(new)
	return out


def open_up(doc):
	"""Every bundle or BOM row of the package's tabs replaced by its items, in its place; then on
	the panel and inverter tabs, each kit led by an option row and its parts never the default."""
	for table in TABLES:
		rows = doc.get(table) or []
		if any(opens(table, r) for r in rows):
			out = []
			for r in rows:
				out.extend(expand(table, r.as_dict()) if opens(table, r) else [r])
			doc.set(table, out)
		if table in OPTION_TABLES:
			tidy_kits(doc.get(table) or [])


def tidy_kits(rows):
	"""A kit whose first row was taken away is led by its next; a part is never the default."""
	led = set()
	for row in rows:
		key = row.get("bundle_key")
		if not row.get("bundle_part"):
			if key:
				led.add(key)
			continue
		if not key or key not in led:
			row.bundle_part = 0
			if key:
				led.add(key)
			continue
		row.is_default = 0


@frappe.whitelist(methods=["POST"])
def expand_row(table, row):
	"""For the package page's row form: the rows a bundle or BOM row opens into."""
	from a3_sola.api.portal_users import require_admin

	require_admin()
	if table not in TABLES:
		frappe.throw(frappe._("Not a table a bundle opens into: {0}.").format(table))
	row = json.loads(row) if isinstance(row, str) else row or {}
	return expand(table, frappe._dict(row))


def is_part(row):
	return cint(row.get("bundle_part"))
