# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package is made of Items: each specification row - panel, inverter, battery,
balance of system, KSEB, mounting, installation, add-on - names an Item of its own category,
and the package itself is the finished good, its name and code the Item's.

The row keeps its specification text beside the Item: the package's prices, the estimate and
the proposal's print read the text, so choosing an Item fills it in (solar_package.js).
"""

import re

import frappe
from frappe import _

#: table -> (item field, text field). KSEB rows are their Item alone.
ROWS = {
	"modules": ("module_item", "module_specification"),
	"inverters": ("inverter_item", "inverter_specification"),
	"batteries": ("battery_item", "specification"),
	"system_items": ("item", "specification"),
	"kseb_expenses": ("particulars", None),
	"mounting_expenses": ("item", "specification"),
	"installation_expenses": ("item", "specification"),
	"optional_add_ons": ("item_code", "item"),
}
#: The item group each table's Items belong to (its subgroups count).
CATEGORY = {
	"modules": "Modules",
	"inverters": "Inverters",
	"batteries": "Batteries",
	"kseb_expenses": "KSEB Expenses",
	"mounting_expenses": "Mounting Structure Expenses",
	"installation_expenses": "Installation Expenses",
	"optional_add_ons": "Optional Add-ons",
}
PACKAGE_GROUP = "Solar Packages"
ADD_ON_GROUP = "Optional Add-ons"
#: Groups of things bought and stocked; the rest are services and fees.
GOODS = {"Modules", "Inverters", "Batteries", "Cables and BOS", "Meters", "Mounting Structures"}


def system_item_group(system_type):
	return {"Solar Energy Meter": "Meters", "Mounting Structure": "Mounting Structures", "Battery": "Batteries"}.get(
		system_type or "", "Cables and BOS")


def category(table, row):
	return system_item_group(row.get("system_type")) if table == "system_items" else CATEGORY.get(table)


def in_group(item, group):
	"""Whether `item` sits in `group` or under it."""
	item_group = frappe.db.get_value("Item", item, "item_group")
	if not item_group or not group:
		return False
	bounds = frappe.db.get_value("Item Group", group, ["lft", "rgt"])
	at = frappe.db.get_value("Item Group", item_group, "lft")
	return bool(bounds and at and bounds[0] <= at <= bounds[1])


def validate(doc):
	"""Every row's Item is of its row's category: no inverter in the panels."""
	for table, (field, _text) in ROWS.items():
		for row in doc.get(table) or []:
			item, group = row.get(field), category(table, row)
			if item and group and not in_group(item, group):
				frappe.throw(_("Row {0} of {1}: {2} is not in the {3} item group.").format(
					row.idx, doc.meta.get_label(table), frappe.bold(item), frappe.bold(group)), title=_("Wrong Item"))


# ------------------------------------------------------------------ making the Items
def leaf_group(table, row, package):
	"""Where a new Item from this row goes: its category's own subgroup where it has them."""
	text = (row.get(ROWS[table][1]) or "").lower() if ROWS[table][1] else ""
	if table == "modules":
		return "TOPCon Modules" if "topcon" in text else "Bifacial Modules" if "bifacial" in text else "Mono PERC Modules"
	if table == "inverters":
		if "hybrid" in text or (package.get("system_type") or "") == "Hybrid":
			return "Hybrid Inverters"
		return "Off-Grid Inverters" if "off-grid" in text or "off grid" in text else "On-Grid Inverters"
	return category(table, row)


#: HSN / SAC by item group, and for balance of system by its type.
HSN = {"Modules": "85414300", "Inverters": "85044090", "Batteries": "85076000", "Cables and BOS": "85444999",
	"Meters": "90283010", "Mounting Structures": "73089090", ADD_ON_GROUP: "995442"}
BOS_HSN = {"DCDB": "85372000", "ACDB": "85372000", "Earthing": "85359090", "Lightning Protection": "85354010"}


def hsn_for(table, row, group):
	top = category(table, row)
	code = (BOS_HSN.get(row.get("system_type")) if table == "system_items" else None) or HSN.get(top) or HSN.get(group)
	if code and frappe.db.exists("DocType", "GST HSN Code") and not frappe.db.exists("GST HSN Code", code):
		return None
	return code


def ensure_group(name, parent="All Item Groups"):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent,
			"is_group": 0}).insert(ignore_permissions=True)


def item_name_for(table, row, text):
	"""The Item's name: the row's text, with its type ahead of it where the text does not say
	it ("DCDB - With PV fuses at input, ...") - the description keeps the text as written."""
	kind = row.get("system_type") if table == "system_items" else None
	if kind and kind != "Other" and kind.lower() not in (text or "").lower():
		return f"{kind} - {text}"
	return text


def item_for(text, group, hsn, top, name=None):
	"""The Item named by this text in its category - the one already there, else a new one."""
	text = re.sub(r"\s+", " ", text or "").strip()
	if not text:
		return None
	name = re.sub(r"\s+", " ", name or text).strip()[:140].strip()
	for match in frappe.get_all("Item", filters={"item_name": name}, pluck="name") + (
			[name] if frappe.db.exists("Item", name) else []):
		if in_group(match, top):
			return match
	code, n = name, 1
	while frappe.db.exists("Item", code):  # the text names an Item of another category
		n += 1
		code = f"{name[:134]} ({n})"
	goods = top in GOODS
	item = frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": name, "description": text,
		"item_group": group, "stock_uom": "Nos", "is_stock_item": 1 if goods else 0,
		"is_purchase_item": 1, "is_sales_item": 1})
	if hsn and item.meta.has_field("gst_hsn_code"):
		item.gst_hsn_code = hsn
	item.insert(ignore_permissions=True)
	return item.name


# ------------------------------------------------------------------ the package's BOM
#: The rows that are materials, with the field holding each one's quantity. KSEB fees, the
#: mounting and installation work and the add-ons are services: priced, never in the BOM.
MATERIAL_ROWS = {"modules": "module_count", "inverters": "inverter_count", "batteries": "nos", "system_items": "qty"}


def _quoted(table, row):
	"""Whether the row is part of the package as quoted: the default panel and inverter, the
	default of each balance-of-system type, every battery that is not an option."""
	if table == "batteries":
		return not row.get("is_option")
	return bool(row.get("is_default"))


def bom_lines(package):
	"""The package's raw materials, item -> quantity, in the order the package lists them."""
	lines = {}
	for table, qty_field in MATERIAL_ROWS.items():
		item_field = ROWS[table][0]
		for row in package.get(table) or []:
			item = row.get(item_field)
			if not item or not _quoted(table, row):
				continue
			lines[item] = lines.get(item, 0) + (frappe.utils.flt(row.get(qty_field)) or 1)
	return lines


def _missing(package):
	"""The quoted rows with no Item yet, as their row labels."""
	out = []
	for table in MATERIAL_ROWS:
		item_field, text_field = ROWS[table]
		for row in package.get(table) or []:
			if _quoted(table, row) and not row.get(item_field):
				out.append("{0} row {1}{2}".format(package.meta.get_label(table), row.idx,
					f" ({row.get(text_field)})" if text_field and row.get(text_field) else ""))
	return out


def _new_bom(package, lines):
	bom = frappe.get_doc({"doctype": "BOM", "item": package.item, "company": package.company, "quantity": 1,
		"is_active": 1, "is_default": 1, "with_operations": 0,
		"items": [{"item_code": item, "qty": qty} for item, qty in lines.items()]})
	# Each line's "valuation rate not found" is noise here: the materials are priced in the package.
	muted, frappe.flags.mute_messages = frappe.flags.mute_messages, True
	try:
		bom.insert(ignore_permissions=True)
		bom.submit()
	finally:
		frappe.flags.mute_messages = muted
	return bom


def _package_for_bom(solar_package):
	package = frappe.get_doc("Solar Package", solar_package)
	package.check_permission("write")
	if not package.item:
		frappe.throw(_("Create the package's Item first."), title=_("No Item"))
	missing = _missing(package)
	if missing:
		frappe.throw(_("Choose an Item on: {0}.").format(", ".join(missing)), title=_("Items Missing"))
	lines = bom_lines(package)
	if not lines:
		frappe.throw(_("The package has no materials to put in a BOM: give its panel, inverter and balance of "
			"system rows their Items."), title=_("No Materials"))
	return package, lines


@frappe.whitelist(methods=["POST"])
def create_bom(solar_package):
	"""The package's BOM: its Item the finished good, its quoted panel, inverter, batteries and
	balance of system the raw materials, each in its own item group."""
	package, lines = _package_for_bom(solar_package)
	if package.bom and frappe.db.exists("BOM", package.bom):
		frappe.throw(_("The package already has BOM {0}: use Update BOM.").format(package.bom))
	bom = _new_bom(package, lines)
	package.db_set("bom", bom.name)
	return {"bom": bom.name, "lines": len(lines)}


@frappe.whitelist(methods=["POST"])
def update_bom(solar_package):
	"""The package's BOM made to match the package again. A BOM in use cannot change, so a
	package that has changed gets a new BOM - the default from now on - and the old one is
	retired; one that has not changed keeps its BOM."""
	package, lines = _package_for_bom(solar_package)
	current = frappe.get_doc("BOM", package.bom) if package.bom and frappe.db.exists("BOM", package.bom) else None
	if not current:
		return create_bom(solar_package) | {"created": 1}
	had = {}
	for row in current.items:
		had[row.item_code] = had.get(row.item_code, 0) + frappe.utils.flt(row.qty)
	changes = changes_between(had, lines)
	if not changes:
		return {"bom": current.name, "unchanged": 1}
	bom = _new_bom(package, lines)
	current.db_set({"is_active": 0, "is_default": 0})
	package.db_set("bom", bom.name)
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Solar Package",
		"reference_name": package.name, "content": _("BOM {0} replaced by {1}: {2}").format(
			current.name, bom.name, "; ".join(changes))}).insert(ignore_permissions=True)
	return {"bom": bom.name, "previous": current.name, "changes": changes}


def changes_between(had, lines):
	"""What changed between the BOM's lines and the package's, as sentences."""
	out = []
	for item, qty in lines.items():
		if item not in had:
			out.append(_("{0} added ({1})").format(item, frappe.utils.flt(qty)))
		elif abs(had[item] - qty) > 1e-9:
			out.append(_("{0}: {1} → {2}").format(item, frappe.utils.flt(had[item]), frappe.utils.flt(qty)))
	out += [_("{0} removed").format(item) for item in had if item not in lines]
	return out
