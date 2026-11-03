# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package's two tables of materials beside its quoted rows: the Material BOM (Inverter
tab) and the Structure BOMs (Mounting tab) - what the system and its mounting structure are
built from, pipes, lugs, clamps, bolts, each an Item with its quantity and rate.

A row says what it goes with, and saying nothing means everything:
- a Material BOM row, the inverter options (their Items);
- a Structure BOM row, the roof types and the system capacities (kW).
The package's BOM takes the rows of its own default inverter, roof type and capacity
(package_items.bom_lines), in each Item's stock UOM.

Both tables come from Excel as often as they are typed: Upload Excel reads a sheet with the
table's columns - Item Name, Category, UOM, Quantity, Rate, Amount and its own "depends on"
columns - finding each Item by its code or name and making the missing ones in their Category.
Download Excel gives the same sheet back, to fill or to edit.
"""

import base64
import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api import package_items

#: The sheet's columns every table has, in order.
COLUMNS = ("Item Name", "Category", "UOM", "Quantity", "Rate", "Amount")
#: A sheet's header -> the row's field, for every table.
HEADERS = {
	"item name": "item", "item": "item", "item code": "item",
	"category": "category", "item group": "category",
	"uom": "uom", "unit": "uom",
	"quantity": "qty", "qty": "qty",
	"rate": "rate",
	"amount": "amount",
}
#: table -> its "depends on" fields: (field, sheet column, the other headers it may go by).
DEPENDS = {
	"material_bom": (
		("inverters", "Depends on Inverter", ("inverter", "inverters", "depends on inverters")),
	),
	"structure_boms": (
		("roof_types", "Depends on Roof Type", ("roof type", "roof types", "depends on roof types")),
		("panel_capacities", "Panel Capacity (kW)", ("panel capacity", "panel capacities", "panal capacity",
			"panal capacity (kw)", "capacity", "capacity (kw)")),
	),
}
#: Inverter Items may hold commas, so their field keeps one per line; the others a list.
STORED_SEPARATOR = {"inverters": "\n", "roof_types": ", ", "panel_capacities": ", "}
#: What a "depends on" cell may say for "every one".
EVERY = {"", "all", "any", "every"}
SEPARATORS = ",;|\n"


def values_of(row, field):
	"""What a row's "depends on" field names; nothing for every one."""
	split = r"\n" if STORED_SEPARATOR[field] == "\n" else r"[,\n]"
	return [v.strip() for v in re.split(split, row.get(field) or "") if v.strip()]


def _store(field, values):
	return STORED_SEPARATOR[field].join(dict.fromkeys(values))


def columns(table):
	return list(COLUMNS) + [heading for _field, heading, _other in DEPENDS[table]]


def default_inverter(package):
	row = next((r for r in package.get("inverters") or [] if r.is_default), None)
	return row.inverter_item if row else None


def applies(table, row, package, inverter=None):
	"""Whether the row is needed for the package as quoted: its default inverter, its roof type
	and its capacity."""
	if table == "material_bom":
		chosen = values_of(row, "inverters")
		return not chosen or inverter in chosen
	roofs, capacities = values_of(row, "roof_types"), [flt(c) for c in values_of(row, "panel_capacities")]
	return (not roofs or package.get("roof_type") in roofs) and (
		not capacities or any(abs(c - flt(package.get("capacity_kw"))) < 0.001 for c in capacities))


# ------------------------------------------------------------------ on save
def validate(doc):
	"""Each row's amount and UOM, and what it depends on only what there is: the package's own
	inverters, roof types, capacities in kW."""
	offered = {r.inverter_item for r in doc.get("inverters") or [] if r.inverter_item}
	for table in DEPENDS:
		label = doc.meta.get_label(table)
		for row in doc.get(table) or []:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0} of {1}: the quantity of {2} must be more than 0.").format(
					row.idx, label, frappe.bold(row.item)), title=_("Wrong Quantity"))
			if not row.uom and row.item:
				row.uom = frappe.db.get_value("Item", row.item, "stock_uom")
			row.amount = flt(flt(row.qty) * flt(row.rate), row.precision("amount"))
			if table == "material_bom":
				unknown = [i for i in values_of(row, "inverters") if i not in offered]
				if unknown:
					frappe.throw(_("Row {0} of {1}: {2} is not one of this package's inverter options. Choose its "
						"inverters again.").format(row.idx, label, ", ".join(frappe.bold(i) for i in unknown)),
						title=_("Wrong Inverter"))
				row.inverters = _store("inverters", values_of(row, "inverters"))
				continue
			unknown = [r for r in values_of(row, "roof_types") if not frappe.db.exists("Roof Type", r)]
			if unknown:
				frappe.throw(_("Row {0} of {1}: there is no Roof Type {2}. Choose its roof types again.").format(
					row.idx, label, ", ".join(frappe.bold(r) for r in unknown)), title=_("Wrong Roof Type"))
			row.roof_types = _store("roof_types", values_of(row, "roof_types"))
			capacities, wrong = _capacities(values_of(row, "panel_capacities"))
			if wrong:
				frappe.throw(_("Row {0} of {1}: {2} is not a capacity in kW.").format(row.idx, label, frappe.bold(wrong)),
					title=_("Wrong Capacity"))
			row.panel_capacities = _store("panel_capacities", capacities)


# ------------------------------------------------------------------ into the package's BOM
def bom_lines(package):
	"""Both tables' rows for the package as quoted, item -> quantity in the Item's stock UOM."""
	inverter = default_inverter(package)
	lines = {}
	for table in DEPENDS:
		for row in package.get(table) or []:
			if row.item and applies(table, row, package, inverter):
				lines[row.item] = lines.get(row.item, 0) + flt(row.qty) * _to_stock_uom(package, table, row)
	return lines


def _to_stock_uom(package, table, row):
	"""How many of the Item's stock UOM one of the row's UOM is."""
	from erpnext.stock.doctype.item.item import get_uom_conv_factor

	stock_uom = frappe.db.get_value("Item", row.item, "stock_uom")
	if not row.uom or row.uom == stock_uom:
		return 1
	factor = frappe.db.get_value("UOM Conversion Detail", {"parenttype": "Item", "parent": row.item, "uom": row.uom},
		"conversion_factor") or get_uom_conv_factor(row.uom, stock_uom)
	if not factor:
		frappe.throw(_("Row {0} of {1}: {2} is counted in {3}, and the row is in {4}. Add {4} to the Item's UOMs, "
			"or give the row the UOM {3}.").format(row.idx, package.meta.get_label(table), frappe.bold(row.item),
			stock_uom, row.uom), title=_("No UOM Conversion"))
	return flt(factor)


# ------------------------------------------------------------------ for the form's pickers
@frappe.whitelist()
def capacities():
	"""The system capacities (kW) the packages are made in, smallest first."""
	frappe.has_permission("Solar Package", "read", throw=True)
	return sorted({flt(c) for c in frappe.get_all("Solar Package", pluck="capacity_kw") if flt(c) > 0})


# ------------------------------------------------------------------ the Excel sheet
@frappe.whitelist(methods=["POST"])
def read_sheet(content, filename, table, inverters=None, company=None):
	"""An uploaded sheet's rows, for the form to put in its `table`.

	`content` is the file as a data URL; `inverters` the form's inverter options as they stand,
	saved or not, and `company` its company, whose roof types a sheet may name. Every row is read
	before anything is made: a sheet with a mistake makes no Items, and its mistakes come back
	together, by the sheet's row numbers."""
	frappe.has_permission("Solar Package", "write", throw=True)
	if table not in DEPENDS:
		frappe.throw(_("Not a table a sheet fills: {0}.").format(table))
	inverters = json.loads(inverters) if isinstance(inverters, str) else inverters or []
	cells = _cells(content, filename)
	start = next((i for i, row in enumerate(cells) if any(_text(c) for c in row)), None)
	if start is None:
		frappe.throw(_("The sheet is empty."), title=_("Nothing to Read"))
	headers = dict(HEADERS)
	for field, heading, others in DEPENDS[table]:
		headers.update({_key(h): field for h in (heading,) + others})
	fields = {i: headers.get(_key(c)) for i, c in enumerate(cells[start])}
	if "item" not in fields.values():
		frappe.throw(_("The sheet has no Item Name column. Its first row should be the headings: {0}.").format(
			", ".join(columns(table))), title=_("No Item Name Column"))
	keys = {"inverters": _inverter_keys(inverters), "roof_types": _roof_keys(company)}
	rows, errors, to_make = [], [], {}
	for n, cells_of_row in enumerate(cells[start + 1:], start=start + 2):
		values = {fields[i]: cell for i, cell in enumerate(cells_of_row) if fields.get(i)}
		if not any(_text(v) for v in values.values()):
			continue
		row, problem = _read_row(table, values, keys, to_make)
		if problem:
			errors.append(_("Row {0}: {1}").format(n, problem))
		else:
			rows.append(row)
	if errors:
		frappe.throw("<br>".join(errors), title=_("The Sheet Has Mistakes"))
	if not rows:
		frappe.throw(_("The sheet has headings and no rows."), title=_("Nothing to Read"))
	made = [_new_item(*spec) for spec in to_make.values()]
	for row in rows:
		if row.get("_new"):
			row["item"] = to_make[row.pop("_new")][0]
	return {"rows": rows, "created": made}


def _read_row(table, values, keys, to_make):
	"""(row, None) for a row that reads, else (None, what is wrong)."""
	name = re.sub(r"\s+", " ", _text(values.get("item"))).strip()[:140].strip()
	if not name:
		return None, _("no Item Name.")
	numbers = {}
	for field, label in (("qty", _("Quantity")), ("rate", _("Rate")), ("amount", _("Amount"))):
		raw = _text(values.get(field)).replace(",", "")
		try:
			numbers[field] = float(raw) if raw else None
		except ValueError:
			return None, _("{0} is not a number for {1}.").format(frappe.bold(raw), label)
	qty = 1 if numbers["qty"] is None else numbers["qty"]
	if qty <= 0:
		return None, _("the quantity of {0} must be more than 0.").format(frappe.bold(name))
	rate = numbers["rate"]
	if rate is None:
		rate = numbers["amount"] / qty if numbers["amount"] is not None else 0
	uom = _text(values.get("uom"))
	if uom:
		uom = frappe.db.exists("UOM", uom)
		if not uom:
			return None, _("there is no UOM {0}.").format(frappe.bold(_text(values.get("uom"))))
	category = _text(values.get("category"))
	item = _find_item(name, category)
	if item and frappe.db.get_value("Item", item, "disabled"):
		return None, _("the Item {0} is disabled.").format(frappe.bold(item))
	row = {"qty": qty, "rate": rate, "amount": qty * rate}
	for field, heading, _others in DEPENDS[table]:
		if field == "panel_capacities":
			chosen, wrong = _capacities(_pieces(values.get(field)))
			if wrong:
				return None, _("{0} is not a capacity in kW.").format(frappe.bold(wrong))
		else:
			chosen, wrong = _match(values.get(field), keys[field])
			if wrong:
				return None, _("{0} under {1} is not one of {2}.").format(frappe.bold(wrong), heading,
					_("this package's inverter options (with an Item)") if field == "inverters" else _("the roof types"))
		row[field] = _store(field, chosen)
	if item:
		group, stock_uom = frappe.db.get_value("Item", item, ["item_group", "stock_uom"])
		return row | {"item": item, "category": group, "uom": uom or stock_uom}, None
	if not category:
		return None, _("there is no Item {0}; give it a Category to make it in.").format(frappe.bold(name))
	group = frappe.db.exists("Item Group", category)
	if not group:
		return None, _("there is no Item Group {0}.").format(frappe.bold(category))
	to_make.setdefault(name.lower(), (name, group, uom or "Nos"))
	return row | {"_new": name.lower(), "category": to_make[name.lower()][1], "uom": uom or to_make[name.lower()][2]}, None


def _find_item(name, category):
	"""The Item a sheet names: by its code, else by its name - the one in the row's Category first."""
	if found := frappe.db.exists("Item", name):
		return found
	matches = frappe.get_all("Item", filters={"item_name": name}, fields=["name", "item_group", "disabled"],
		order_by="disabled asc, creation asc")
	in_category = [m for m in matches if category and m.item_group.lower() == category.lower()]
	return (in_category or matches or [frappe._dict(name=None)])[0].name


def _new_item(name, group, uom):
	item = frappe.get_doc({"doctype": "Item", "item_code": name, "item_name": name, "description": name,
		"item_group": group, "stock_uom": uom, "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 1})
	hsn = _hsn(group)
	if hsn and item.meta.has_field("gst_hsn_code"):
		item.gst_hsn_code = hsn
	item.insert(ignore_permissions=True)
	return item.name


def _hsn(group):
	"""The HSN of the package category the group sits under, where there is one."""
	at = frappe.db.get_value("Item Group", group, "lft")
	for top, code in package_items.HSN.items():
		bounds = frappe.db.get_value("Item Group", top, ["lft", "rgt"])
		if at and bounds and bounds[0] <= at <= bounds[1]:
			if frappe.db.exists("DocType", "GST HSN Code") and not frappe.db.exists("GST HSN Code", code):
				return None
			return code
	return None


def _inverter_keys(inverters):
	"""What a sheet may call each inverter option -> its Item: the Item's code, its name, or the
	row's specification."""
	keys = {}
	for inv in inverters:
		item = inv.get("inverter_item")
		if not item:
			continue
		for text in (item, frappe.db.get_value("Item", item, "item_name"), inv.get("inverter_specification")):
			if _key(text):
				keys[_key(text)] = item
	return keys


def _roof_keys(company=None):
	"""What a sheet may call each roof type -> its name: the name, or the roof type it says."""
	filters = {"company": company} if company else {}
	keys = {}
	for roof in frappe.get_all("Roof Type", filters=filters, fields=["name", "roof_type"]):
		keys[_key(roof.name)] = roof.name
		if _key(roof.roof_type):
			keys[_key(roof.roof_type)] = roof.name
	return keys


def _match(cell, keys):
	"""(the names a cell gives, None), else ([], the text it does not know).

	The names may be split by commas, semicolons, bars or lines, and a name may hold a comma
	itself, so pieces are joined until they make a name."""
	text = _text(cell)
	if _key(text) in EVERY:
		return [], None
	chosen, piece = [], ""
	for part in re.split(f"([{re.escape(SEPARATORS)}])", text):
		piece += part
		key = _key(piece.strip(SEPARATORS + " \t"))
		if key in keys:
			chosen.append(keys[key])
			piece = ""
	left = piece.strip(SEPARATORS + " \t")
	return (list(dict.fromkeys(chosen)), None) if not left else ([], left)


def _pieces(cell):
	text = _text(cell)
	return [] if _key(text) in EVERY else [p for p in re.split(f"[{re.escape(SEPARATORS)}]", text) if p.strip()]


def _capacities(pieces):
	"""(capacities in kW, smallest first, as they are written; None), else ([], the piece that is
	not one). "3", "3 kW" and "3.0" are all 3."""
	out = set()
	for piece in pieces:
		raw = re.sub(r"\s*kw[p]?$", "", piece.strip(), flags=re.IGNORECASE)
		try:
			kw = float(raw)
		except ValueError:
			return [], piece.strip()
		if kw <= 0:
			return [], piece.strip()
		out.add(kw)
	return ["{0:g}".format(kw) for kw in sorted(out)], None


@frappe.whitelist(methods=["POST"])
def download_sheet(table, rows=None, package=None):
	"""A table as a sheet, in the columns Upload Excel reads; headings alone for an empty table,
	as a template. Roof types are written as they read, not by their codes."""
	from frappe.utils.xlsxutils import build_xlsx_response

	frappe.has_permission("Solar Package", "read", throw=True)
	if table not in DEPENDS:
		frappe.throw(_("Not a table a sheet fills: {0}.").format(table))
	rows = json.loads(rows) if isinstance(rows, str) else rows or []
	roofs = dict(frappe.get_all("Roof Type", fields=["name", "roof_type"], as_list=True))
	data = [columns(table)]
	for r in rows:
		line = [r.get("item"), r.get("category"), r.get("uom"), flt(r.get("qty")), flt(r.get("rate")), flt(r.get("amount"))]
		for field, _heading, _others in DEPENDS[table]:
			names = values_of(r, field)
			if field == "roof_types":
				names = [roofs.get(n) or n for n in names]
			line.append(", ".join(names))
		data.append(line)
	name = re.sub(r"[^\w\- ]+", "", package or "") or _("New Package")
	label = frappe.get_meta("Solar Package").get_label(table)
	build_xlsx_response(data, "{0} - {1}".format(label, name))


# ------------------------------------------------------------------ reading the file
def _cells(content, filename):
	data = base64.b64decode(content.split(",", 1)[1] if content.startswith("data:") else content)
	extension = (filename or "").rsplit(".", 1)[-1].lower()
	if extension == "xlsx":
		from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

		return read_xlsx_file_from_attached_file(fcontent=data) or []
	if extension == "csv":
		from frappe.utils.csvutils import read_csv_content

		return read_csv_content(data) or []
	frappe.throw(_("Upload an Excel (.xlsx) or CSV file."), title=_("Wrong File"))


def _text(value):
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value).strip()


def _key(value):
	return re.sub(r"\s+", " ", _text(value)).strip().lower()
