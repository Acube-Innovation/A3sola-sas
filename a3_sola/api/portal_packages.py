# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's Packages page: an admin adds, edits, duplicates, activates or deletes the
Solar Packages estimates and proposals are built from - every table of the desk form - and
makes the package's Item and BOM, all without the ERPNext desk.

Only an admin may use any of it (api/portal_users.is_user_admin); staff still read Active
packages where an estimate offers them. The page posts the whole package and the server's own
rules (solar_package.py validate) decide what is right: item categories, one default, the
panels each inverter is built with, the computed KSEB, mounting and installation rows. The
price, subsidy and net rate are worked out from the inverter options (solar_package.price_for).

A package an estimate, project or quotation names cannot go: it is set to Draft instead, so
it is no longer offered and the records made from it keep it.
"""

import html
import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, format_datetime

from a3_sola.api.package_items import CATEGORY
from a3_sola.api.portal_users import require_admin

DOCTYPE = "Solar Package"
#: The desk form's tab key the page knows each tab by (its Battery tab shows for Off-Grid and
#: Hybrid only, its BOM tab carries the payment terms); any other tab goes by its fieldname.
TAB_KEYS = {"tab_package": "package", "tab_battery": "batteries", "tab_commercial": "cost"}
#: Made by the page's buttons, never typed.
SET_BY_BUTTONS = {"item", "bom"}
#: The BOM tab's "depends on" fields: read-only on the desk, where a dialog sets them; the page's
#: row form sets them the same way, so a save takes them (package_bom_tables.validate checks).
PICKED = {"material_bom": ("inverters",), "structure_boms": ("roof_types", "panel_capacities")}
#: The item a row names, and the text its choice fills in (solar_package.js ITEM_ROWS).
ITEM_TEXT = {
	"modules": ("module_item", "module_specification"),
	"inverters": ("inverter_item", "inverter_specification"),
	"batteries": ("battery_item", "specification"),
	"system_items": ("item", "specification"),
	"optional_add_ons": ("item_code", "item"),
}
#: The expense tables offer their own group's items exactly, not its subgroups.
EXACT_GROUP = {"kseb_expenses", "mounting_expenses", "installation_expenses"}
ITEM_GROUPS = ("Modules", "Inverters", "Batteries", "Meters", "Mounting Structures", "Cables and BOS",
	"Optional Add-ons", "KSEB Expenses", "Mounting Structure Expenses", "Installation Expenses")
FIELD_TYPES = {"Data", "Select", "Link", "Float", "Int", "Currency", "Percent", "Check", "Small Text", "Text"}
ITEM_LIMIT = 3000


# ------------------------------------------------------------------ the list
@frappe.whitelist()
def packages():
	require_admin()
	from a3_sola.solar_crm.doctype.solar_package.solar_package import default_prices

	rows = frappe.get_all(DOCTYPE, fields=["name", "specification_code", "package_name", "capacity_kw", "system_type",
		"connection_type", "tier", "status", "is_active", "item", "bom", "company", "modified"],
		order_by="capacity_kw asc, package_name asc")
	prices = default_prices([r.name for r in rows])
	counts = {"Active": 0, "Draft": 0}
	for r in rows:
		r.status = r.status or "Draft"
		counts[r.status] = counts.get(r.status, 0) + 1
		price = prices.get(r.name)
		r.net_rate = flt(price.net_rate) if price else 0
		r.system_cost = flt(price.system_cost) if price else 0
		r.modified = format_datetime(r.modified, "d MMM yyyy")
	return {"packages": rows, "counts": counts, "total": len(rows)}


# ------------------------------------------------------------------ one package, for the editor
def _spec(df, parent=False):
	return {"fieldname": df.fieldname, "label": _(df.label or df.fieldname), "type": df.fieldtype,
		"options": df.options if df.fieldtype == "Link" else [o for o in (df.options or "").split("\n")]
			if df.fieldtype == "Select" else None,
		"reqd": cint(df.reqd), "read_only": cint(df.read_only) or (parent and df.fieldname in SET_BY_BUTTONS),
		"in_list": cint(df.in_list_view), "description": df.description or "", "default": df.default}


def _table(fieldname):
	df = frappe.get_meta(DOCTYPE).get_field(fieldname)
	child = frappe.get_meta(df.options)
	columns = [_spec(f) for f in child.fields if f.fieldtype in FIELD_TYPES and not cint(f.hidden)]
	return {"fieldname": fieldname, "label": _(df.label), "doctype": df.options, "columns": columns}


def _layout():
	"""The desk form's tabs as the page shows them: each tab's sections, each section's columns,
	each column its fields, tables and HTML in the desk's order. Hidden tabs, sections and
	fields are left out, as the desk leaves them out."""
	meta = frappe.get_meta(DOCTYPE)
	tabs, tab, section, hidden_tab, hidden_section = [], None, None, False, False

	def new_section(label=""):
		tab["sections"].append({"label": _(label) if label else "", "columns": [[]]})
		return tab["sections"][-1]

	for df in meta.fields:
		if df.fieldtype == "Tab Break":
			hidden_tab = cint(df.hidden)
			if hidden_tab:
				continue
			tab = {"key": TAB_KEYS.get(df.fieldname, df.fieldname), "label": _(df.label), "fields": [], "tables": [],
				"sections": []}
			tabs.append(tab)
			section, hidden_section = None, False
			continue
		if hidden_tab or tab is None:
			continue
		if df.fieldtype == "Section Break":
			hidden_section = cint(df.hidden)
			section = None if hidden_section else new_section(df.label)
			continue
		if hidden_section or cint(df.hidden):
			continue
		if df.fieldtype == "Column Break":
			if section:
				section["columns"].append([])
			continue
		section = section or new_section()
		if df.fieldtype == "Table":
			tab["tables"].append(df.fieldname)
			section["columns"][-1].append({"table": df.fieldname})
		elif df.fieldtype == "HTML":
			section["columns"][-1].append({"html": df.fieldname})
		elif df.fieldtype in FIELD_TYPES:
			tab["fields"].append(df.fieldname)
			section["columns"][-1].append({"field": df.fieldname})
	for tab in tabs:
		tab["sections"] = [s for s in tab["sections"] if any(s["columns"])]
		for s in tab["sections"]:
			s["columns"] = [c for c in s["columns"] if c]
	return tabs


def _table_fields():
	return [t for tab in _layout() for t in tab["tables"]]


def _rows(doc, fieldname, columns):
	keep = ["name"] + [c["fieldname"] for c in columns]
	return [{k: row.get(k) for k in keep} for row in doc.get(fieldname) or []]


def _assemblies():
	"""The Items that are ERPNext Product Bundles or have an active BOM, as {item: "Bundle" | "BOM"}
	- not the packages' own Items, whose BOM is the package's."""
	from a3_sola.api.package_items import PACKAGE_GROUP

	out = {}
	for item in frappe.get_all("BOM", filters={"is_active": 1, "docstatus": 1}, pluck="item"):
		out[item] = "BOM"
	if frappe.db.exists("DocType", "Product Bundle"):
		filters = {"disabled": 0} if frappe.get_meta("Product Bundle").has_field("disabled") else {}
		for item in frappe.get_all("Product Bundle", filters=filters, pluck="new_item_code"):
			out[item] = "Bundle"
	packages = set(frappe.get_all("Item", filters={"name": ["in", list(out)], "item_group": PACKAGE_GROUP}, pluck="name")) if out else set()
	return {item: kind for item, kind in out.items() if item not in packages}


def _tagged(label, kind):
	"""A Product Bundle or an Item with a BOM, said so ahead of its name: "Bundle: HOYM ..."."""
	return "{0}: {1}".format(kind, label) if kind else label


def _item_choices(assemblies=None):
	"""Each category group's Items - its subgroups' too - with the text a choice fills in, the
	Product Bundles and the Items with a BOM among them tagged so and listed first
	(package_bom_tree); a bundle or BOM of no category group is in every list."""
	assemblies = _assemblies() if assemblies is None else assemblies
	groups = {g.name: (g.lft, g.rgt) for g in frappe.get_all("Item Group", filters={"name": ["in", list(ITEM_GROUPS)]},
		fields=["name", "lft", "rgt"])}
	at = {g.name: g.lft for g in frappe.get_all("Item Group", fields=["name", "lft"])}
	items = frappe.get_all("Item", filters={"disabled": 0, "item_group": ["in", _under(groups)]},
		fields=["name", "item_name", "item_group", "description"], order_by="item_name asc", limit_page_length=ITEM_LIMIT)
	listed = {i.name for i in items}
	items += frappe.get_all("Item", filters={"disabled": 0, "name": ["in", [a for a in assemblies if a not in listed]]},
		fields=["name", "item_name", "item_group", "description"], order_by="item_name asc") if assemblies else []
	out = {g: [] for g in groups}
	for item in items:
		text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", item.description or ""))).strip() or item.item_name
		kind = assemblies.get(item.name)
		entry = {"value": item.name, "label": _tagged(item.item_name if item.item_name == item.name else
			"{0} ({1})".format(item.item_name, item.name), kind), "text": text, "group": item.item_group, "kind": kind}
		# Each Item in its own category's list - a bundle or a BOM too, so an inverter bundle is
		# not offered as a panel; one of no category is offered in every list.
		homes = [g for g, (lft, rgt) in groups.items() if lft <= at.get(item.item_group, -1) <= rgt]
		for group in homes or (list(groups) if kind else []):
			out[group].append(entry)
	# The bundles and BOMs first, then the plain Items, each by name.
	order = {"Bundle": 0, "BOM": 1}
	for entries in out.values():
		entries.sort(key=lambda e: (order.get(e["kind"], 2), e["label"].lower()))
	return out


def _under(groups):
	if not groups:
		return []
	names = set()
	for lft, rgt in groups.values():
		names |= set(frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"))
	return list(names)


def _milestones():
	out = {}
	for row in frappe.get_all("Billing Milestone Template Detail", filters={"parenttype": "Billing Milestone Template"},
			fields=["parent", "milestone_name", "trigger_type", "trigger_stage_code", "percentage", "is_advance"],
			order_by="parent, idx"):
		out.setdefault(row.parent, []).append({"name": row.milestone_name, "when": row.trigger_type +
			(" · " + row.trigger_stage_code if row.trigger_stage_code else ""), "percent": flt(row.percentage),
			"advance": cint(row.is_advance)})
	return out


def _choices():
	"""Every dropdown the form has, loaded once; the page narrows them as the desk's queries do."""
	from a3_sola.api.package_bom_tables import capacities
	from a3_sola.api.permissions import get_permitted_companies

	makes =frappe.get_all("Component Make", fields=["name", "make_name", "component_type", "technology", "company",
		"is_active"], order_by="make_name asc")
	models = frappe.get_all("Inverter Model", filters={"is_active": 1}, fields=["name", "model_name", "inverter_make",
		"inverter_phase", "capacity_kw"], order_by="inverter_make, inverter_phase, capacity_kw")
	make_name = {m.name: m.make_name for m in makes}
	milestones = _milestones()
	companies = get_permitted_companies() or frappe.get_all("Company", pluck="name")
	assemblies = _assemblies()
	return {
		"items": _item_choices(assemblies),
		"Component Make": [{"value": m.name, "label": m.make_name or m.name, "type": m.component_type,
			"technology": m.technology, "company": m.company, "active": cint(m.is_active)} for m in makes],
		"Inverter Model": [{"value": m.name, "label": "{0}, {1}, {2}, {3:g} kW".format(m.model_name,
			make_name.get(m.inverter_make) or m.inverter_make or "", m.inverter_phase or "", flt(m.capacity_kw)),
			"make": m.inverter_make, "phase": m.inverter_phase} for m in models],
		"Component Technology": [{"value": t.name, "label": t.technology_name or t.name, "type": t.component_type,
			"company": t.company} for t in frappe.get_all("Component Technology", filters={"is_active": 1},
				fields=["name", "technology_name", "component_type", "company"], order_by="technology_name")],
		"Roof Type": [{"value": r.name, "label": r.roof_type or r.name, "company": r.company} for r in
			frappe.get_all("Roof Type", fields=["name", "roof_type", "company"], order_by="roof_type")],
		"Billing Milestone Template": [{"value": t.name, "label": t.template_name or t.name, "company": t.company,
			"milestones": milestones.get(t.name, [])} for t in frappe.get_all("Billing Milestone Template",
				filters={"is_active": 1}, fields=["name", "template_name", "company"], order_by="template_name")],
		"BOM": [{"value": b.name, "label": "{0} ({1})".format(b.name, b.item)} for b in frappe.get_all("BOM",
			filters={"docstatus": 1, "is_active": 1}, fields=["name", "item"], order_by="name desc", limit_page_length=2000)],
		"UOM": [{"value": u, "label": u} for u in frappe.get_all("UOM", filters={"enabled": 1}, pluck="name", order_by="name")],
		"Company": [{"value": c, "label": c} for c in companies],
		# The BOM tab's tables take any Item; choosing one fills its Category and UOM.
		"Item": sorted([{"value": i.name, "label": _tagged(i.item_name if i.item_name == i.name else "{0} ({1})".format(i.item_name, i.name),
			assemblies.get(i.name)), "group": i.item_group, "uom": i.stock_uom, "kind": assemblies.get(i.name)} for i in frappe.get_all("Item", filters={"disabled": 0},
				fields=["name", "item_name", "item_group", "stock_uom"], order_by="item_name asc", limit_page_length=ITEM_LIMIT)],
			# The bundles and BOMs first.
			key=lambda e: ({"Bundle": 0, "BOM": 1}.get(e["kind"], 2), e["label"].lower())),
		# Structure BOM rows' Panel Capacity choices: the capacities packages are made in.
		"capacities": capacities(),
	}


@frappe.whitelist()
def package(name=None, copy_from=None):
	"""The package for the editor: its fields, every table, the dropdowns and what its buttons
	can do. `copy_from` gives a new package made from another one."""
	require_admin()
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
	elif copy_from:
		doc = frappe.copy_doc(frappe.get_doc(DOCTYPE, copy_from))
		doc.update({"item": None, "bom": None, "status": "Draft", "is_active": 1,
			"package_name": _("{0} (copy)").format(doc.package_name), "specification_code": ""})
		for fieldname in _table_fields():
			for row in doc.get(fieldname) or []:
				row.name = None
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	meta = frappe.get_meta(DOCTYPE)
	tabs, tables = _layout(), {}
	for tab in tabs:
		tab["fields"] = [_spec(meta.get_field(f), parent=True) for f in tab["fields"]]
		for t in tab["tables"]:
			spec = _table(t)
			spec["rows"] = _rows(doc, t, spec["columns"])
			tables[t] = spec
	values = {f["fieldname"]: doc.get(f["fieldname"]) for tab in tabs for f in tab["fields"]}
	# Not on the form, but every choice the page offers is narrowed to it.
	values["company"] = doc.company
	if not doc.get("name") or doc.is_new():
		values.setdefault("status", "Draft")
	return {"name": None if doc.is_new() else doc.name, "title": doc.package_name or _("New package"),
		"values": values, "tabs": tabs, "tables": tables, "choices": _choices(),
		"item_text": ITEM_TEXT, "exact_group": list(EXACT_GROUP), "category": CATEGORY,
		"modified": str(doc.modified) if not doc.is_new() else None}


# ------------------------------------------------------------------ saving
def _editable(spec):
	picked = PICKED.get(spec["fieldname"], ())
	return [c["fieldname"] for c in spec["columns"] if not c["read_only"] or c["fieldname"] in picked]


def _merge_rows(doc, fieldname, posted):
	"""The table in the posted order: a row the page knew (by `name`) is updated in place, so
	what the page does not show - a computed row's `source` - stays; a new one is added."""
	spec = _table(fieldname)
	editable = _editable(spec)
	had = {row.name: row for row in doc.get(fieldname) or []}
	out = []
	for row in posted or []:
		base = had[row["name"]].as_dict() if row.get("name") in had else {}
		for key in ("parent", "parenttype", "parentfield", "idx", "creation", "modified", "owner", "modified_by", "docstatus"):
			base.pop(key, None)
		base.update({k: row.get(k) for k in editable if k in row})
		out.append(base)
	doc.set(fieldname, out)


@frappe.whitelist(methods=["POST"])
def save_package(data):
	"""Save the package as the page has it - its fields and every table - by the doctype's own
	rules, and return it as saved."""
	require_admin()
	data = json.loads(data) if isinstance(data, str) else data
	name = data.get("name")
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if data.get("modified") and str(doc.modified) != data["modified"]:
			frappe.throw(_("Someone else saved this package while you were editing it. Reload the page to see their "
				"change, then make yours again."), title=_("Package Changed"))
	else:
		doc = frappe.new_doc(DOCTYPE)
	meta = frappe.get_meta(DOCTYPE)
	for fieldname, value in (data.get("values") or {}).items():
		df = meta.get_field(fieldname)
		if df and fieldname not in SET_BY_BUTTONS and not cint(df.read_only):
			doc.set(fieldname, value)
	for fieldname, rows in (data.get("tables") or {}).items():
		if meta.get_field(fieldname) and meta.get_field(fieldname).fieldtype == "Table":
			_merge_rows(doc, fieldname, rows)
	doc.save()
	return package(doc.name)


# ------------------------------------------------------------------ Item, BOM, status
@frappe.whitelist(methods=["POST"])
def create_item(name):
	require_admin()
	from a3_sola.solar_crm.doctype.solar_package.solar_package import create_item_and_bom

	result = create_item_and_bom(name)
	return {"result": result, "package": package(name)}


@frappe.whitelist(methods=["POST"])
def create_bom(name):
	require_admin()
	from a3_sola.api import package_items

	result = package_items.create_bom(name)
	return {"result": result, "package": package(name)}


@frappe.whitelist(methods=["POST"])
def update_bom(name):
	require_admin()
	from a3_sola.api import package_items

	result = package_items.update_bom(name)
	return {"result": result, "package": package(name)}


@frappe.whitelist()
def bom(name):
	"""The package's BOM, read-only: its finished good and raw materials."""
	require_admin()
	bom_name = frappe.db.get_value(DOCTYPE, name, "bom")
	if not bom_name or not frappe.db.exists("BOM", bom_name):
		frappe.throw(_("This package has no BOM yet."))
	b = frappe.get_doc("BOM", bom_name)
	return {"name": b.name, "item": b.item, "item_name": b.item_name, "is_active": b.is_active, "is_default": b.is_default,
		"total": flt(b.total_cost), "rows": [{"item_code": r.item_code, "item_name": r.item_name, "qty": flt(r.qty),
			"uom": r.uom, "rate": flt(r.rate), "amount": flt(r.amount)} for r in b.items]}


@frappe.whitelist(methods=["POST"])
def set_status(name, status):
	require_admin()
	if status not in ("Draft", "Active"):
		frappe.throw(_("A package is Draft or Active."))
	doc = frappe.get_doc(DOCTYPE, name)
	doc.status = status
	# Draft and Active packages are both offered in estimates; Active brings back a retired one.
	if status == "Active":
		doc.is_active = 1
	doc.save()
	return {"name": name, "status": status}


@frappe.whitelist(methods=["POST"])
def delete_package(name):
	"""Deleted - with its own BOM and Item, where nothing else uses them - if no record names
	the package; else set to Draft, so it is no longer offered and those records keep it."""
	require_admin()
	doc = frappe.get_doc(DOCTYPE, name)
	item, bom_name = doc.item, doc.bom
	frappe.db.savepoint("portal_package_delete")
	try:
		frappe.delete_doc(DOCTYPE, name)
	except (frappe.LinkExistsError, frappe.ValidationError):
		frappe.db.rollback(save_point="portal_package_delete")
		frappe.clear_messages()
		doc = frappe.get_doc(DOCTYPE, name)
		# Retired: Draft and inactive, so estimates no longer offer it.
		doc.status, doc.is_active = "Draft", 0
		doc.save()
		return {"deleted": 0, "draft": 1, "message": _("{0} is used in estimates, projects or quotations, so it was set "
			"to Draft instead of deleted. It is no longer offered for new estimates.").format(doc.package_name)}
	kept = []
	for doctype, record in (("BOM", bom_name), ("Item", item)):
		if not record or not frappe.db.exists(doctype, record):
			continue
		frappe.db.savepoint("portal_package_parts")
		try:
			if doctype == "BOM" and frappe.db.get_value("BOM", record, "docstatus") == 1:
				frappe.get_doc("BOM", record).cancel()
			frappe.delete_doc(doctype, record, ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point="portal_package_parts")
			frappe.clear_messages()
			kept.append(record)
	return {"deleted": 1, "kept": kept}
