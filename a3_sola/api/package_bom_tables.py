# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Solar Package's tables of Items beside its quoted rows, each on a tab of its own: the
Material BOM and the Structure BOMs - what the system and its mounting structure are built
from, pipes, lugs, clamps, bolts, each an Item with its quantity and rate - and the Expenses,
what the package costs to build, a costing record that goes into no BOM.

A row may depend on Items of the package's own - its panels', inverters', batteries', balance
of system's, KSEB, mounting and installation rows' Items, Product Bundles and BOMs among them.
It is then taken only where one of those is used: by the package as quoted (its default panel
and inverter, and so on - used_items), or by the design estimate it is copied to. A row that
depends on none is always taken. The package's BOM takes the rows of what it uses (bom_lines),
in each Item's stock UOM.

Every table comes from Excel as often as it is typed: Upload Excel reads a sheet with the
columns Item Name, Item Description, Category, UOM, Quantity, Rate, Amount and Depends On,
finding each Item by its code or name and making the missing ones in their Category.
Download Excel gives the same sheet back, to fill or to edit.
"""

import base64
import html
import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api import package_items

#: The tables, a tab each.
TABLES = ("material_bom", "structure_boms", "expenses")
#: The tables that go into the package's BOM (package_items.bom_lines); Expenses do not.
BOM_TABLES = ("material_bom", "structure_boms")
#: The sheet's columns, in order.
COLUMNS = ("Item Name", "Item Description", "Category", "UOM", "Quantity", "Rate", "Amount", "Depends On")
#: A sheet's header -> the row's field. An older sheet's Depends on Inverter column is read as
#: Depends On; its roof type and capacity columns are not read.
HEADERS = {
	"item name": "item", "item": "item", "item code": "item",
	"item description": "description", "description": "description",
	"category": "category", "item group": "category",
	"uom": "uom", "unit": "uom",
	"quantity": "qty", "qty": "qty",
	"rate": "rate",
	"amount": "amount",
	"depends on": "depends_on", "depends on item": "depends_on", "depends on items": "depends_on",
	"depends on inverter": "depends_on", "depends on inverters": "depends_on", "inverter": "depends_on",
	"inverters": "depends_on",
}
#: The package's rows that name its own Items: (table, the Item's field).
OWN_ITEMS = (("modules", "module_item"), ("inverters", "inverter_item"), ("batteries", "battery_item"),
	("system_items", "item"), ("kseb_expenses", "particulars"), ("mounting_expenses", "item"),
	("installation_expenses", "item"))
#: What a Depends On cell may say for "none".
EVERY = {"", "all", "any", "every", "none"}
SEPARATORS = ",;|\n"


def columns(table=None):
	return list(COLUMNS)


def depends_on(row):
	"""The Items a row depends on - one per line, as an Item may hold a comma; none, always taken."""
	return [v.strip() for v in (row.get("depends_on") or "").split("\n") if v.strip()]


def own_items(package):
	"""The Items the package's other tabs name, in tab order, each once: what a row may depend on."""
	return list(dict.fromkeys(row.get(field) for table, field in OWN_ITEMS for row in package.get(table) or []
		if row.get(field)))


def used_items(package, chosen=None):
	"""The Items the package as quoted uses: its default panel and inverter (a kit's parts too),
	the default of each balance-of-system type, every battery that is not an option
	(package_items.quoted_rows), and every KSEB, mounting and installation row's. `chosen` gives
	other rows for a table - a Pricing Options row's panel, inverter and battery."""
	chosen = chosen or {}

	def rows(table):
		if table in chosen:
			return chosen[table]
		return package_items.quoted_rows(package, table) if table in package_items.MATERIAL_ROWS else package.get(table) or []

	return {row.get(field) for table, field in OWN_ITEMS for row in rows(table) if row.get(field)}


def applies(row, used):
	"""Whether a row is taken where `used` are the Items in use: one it depends on is, or it
	depends on none."""
	chosen = depends_on(row)
	return not chosen or any(item in used for item in chosen)


def item_text(item):
	"""An Item's description as plain text, else its name."""
	name, description = frappe.db.get_value("Item", item, ["item_name", "description"]) or (None, None)
	text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", description or ""))).strip()
	return text or name or ""


# ------------------------------------------------------------------ on save
def validate(doc):
	"""Each row's amount, its UOM and description where blank (the Item's), and what it depends on
	only the package's own Items."""
	own = set(own_items(doc))
	for table in TABLES:
		label = doc.meta.get_label(table)
		for row in doc.get(table) or []:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0} of {1}: the quantity of {2} must be more than 0.").format(
					row.idx, label, frappe.bold(row.item)), title=_("Wrong Quantity"))
			if row.item and not row.uom:
				row.uom = frappe.db.get_value("Item", row.item, "stock_uom")
			if row.item and not (row.description or "").strip():
				row.description = item_text(row.item)
			row.amount = flt(flt(row.qty) * flt(row.rate), row.precision("amount"))
			unknown = [i for i in depends_on(row) if i not in own]
			if unknown:
				frappe.throw(_("Row {0} of {1}: {2} is not one of this package's Items. Choose what it depends on "
					"again.").format(row.idx, label, ", ".join(frappe.bold(i) for i in unknown)),
					title=_("Wrong Depends On"))
			row.depends_on = "\n".join(dict.fromkeys(depends_on(row)))


# ------------------------------------------------------------------ into the package's BOM
def bom_lines(package):
	"""Both tables' rows for the package as quoted, item -> quantity in the Item's stock UOM.

	The rows typed into the tables (package_bom_tree.is_own) that apply to what the package uses:
	an Item with a BOM as itself, a sub-assembly; a Product Bundle as its items, which an ERPNext
	BOM holds and a bundle it cannot."""
	from a3_sola.api.package_bom_tree import is_own, line_items

	used = used_items(package)
	lines, made = {}, {}
	for table in BOM_TABLES:
		for row in package.get(table) or []:
			if not (row.item and is_own(row) and applies(row, used)):
				continue
			parts = line_items(row.item, flt(row.qty), made)
			if parts == [(row.item, flt(row.qty))]:
				parts = [(row.item, flt(row.qty) * _to_stock_uom(package, table, row))]
			for item, qty in parts:
				lines[item] = lines.get(item, 0) + qty
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


# ------------------------------------------------------------------ the Excel sheet
@frappe.whitelist(methods=["POST"])
def read_sheet(content, filename, table, items=None, company=None):
	"""An uploaded sheet's rows, for the form to put in its `table`.

	`content` is the file as a data URL; `items` the Items the form's other tabs name as they
	stand, saved or not - what a row may depend on. Every row is read before anything is made: a
	sheet with a mistake makes no Items, and its mistakes come back together, by the sheet's row
	numbers."""
	frappe.has_permission("Solar Package", "write", throw=True)
	if table not in TABLES:
		frappe.throw(_("Not a table a sheet fills: {0}.").format(table))
	items = json.loads(items) if isinstance(items, str) else items or []
	cells = _cells(content, filename)
	start = next((i for i, row in enumerate(cells) if any(_text(c) for c in row)), None)
	if start is None:
		frappe.throw(_("The sheet is empty."), title=_("Nothing to Read"))
	fields = {i: HEADERS.get(_key(c)) for i, c in enumerate(cells[start])}
	if "item" not in fields.values():
		frappe.throw(_("The sheet has no Item Name column. Its first row should be the headings: {0}.").format(
			", ".join(COLUMNS)), title=_("No Item Name Column"))
	keys = _item_keys(items)
	rows, errors, to_make = [], [], {}
	for n, cells_of_row in enumerate(cells[start + 1:], start=start + 2):
		values = {fields[i]: cell for i, cell in enumerate(cells_of_row) if fields.get(i)}
		if not any(_text(v) for v in values.values()):
			continue
		row, problem = _read_row(values, keys, to_make)
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


def _read_row(values, keys, to_make):
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
	chosen, wrong = _match(values.get("depends_on"), keys)
	if wrong:
		return None, _("{0} under Depends On is not one of this package's Items.").format(frappe.bold(wrong))
	row = {"qty": qty, "rate": rate, "amount": qty * rate, "description": _text(values.get("description")),
		"depends_on": "\n".join(chosen)}
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


def _item_keys(items):
	"""What a sheet may call each of the package's Items -> the Item: its code or its name."""
	keys = {}
	for item in items:
		if not item:
			continue
		for text in (item, frappe.db.get_value("Item", item, "item_name")):
			if _key(text):
				keys[_key(text)] = item
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


@frappe.whitelist(methods=["POST"])
def download_sheet(table, rows=None, package=None):
	"""A table as a sheet, in the columns Upload Excel reads; headings alone for an empty table,
	as a template."""
	from frappe.utils.xlsxutils import build_xlsx_response

	frappe.has_permission("Solar Package", "read", throw=True)
	if table not in TABLES:
		frappe.throw(_("Not a table a sheet fills: {0}.").format(table))
	rows = json.loads(rows) if isinstance(rows, str) else rows or []
	data = [list(COLUMNS)]
	for r in rows:
		data.append([r.get("item"), r.get("description"), r.get("category"), r.get("uom"), flt(r.get("qty")),
			flt(r.get("rate")), flt(r.get("amount")), "\n".join(depends_on(r))])
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
