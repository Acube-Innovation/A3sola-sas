# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A project's structure bill of materials - the pipes, consumables, bolts and caps the
mounting structure is built from.

Each Solar Package lists its structure BOMs (ERPNext BOMs) by roof type and panel capacity.
A project takes the one for its own roof type at its capacity, else the next larger one -
a structure built for more panels carries fewer - else the largest there is.
"""

import frappe
from frappe import _
from frappe.utils import flt


def bom_for(installation):
	"""The structure BOM for a project (a Solar Installation, or its name), or None."""
	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	if not (inst.get("solar_package") and inst.get("roof_type")):
		return None
	rows = frappe.get_all(
		"Solar Package Structure BOM",
		filters={"parent": inst.solar_package, "parenttype": "Solar Package", "roof_type": inst.roof_type},
		fields=["panel_capacity_kw", "bom"], order_by="panel_capacity_kw asc",
	)
	return pick(rows, flt(inst.get("capacity_kw")))


def pick(rows, capacity):
	"""Of `rows` ({panel_capacity_kw, bom}), the one for `capacity`: exact, else the next larger,
	else the largest."""
	rows = sorted((r for r in rows if r.get("bom")), key=lambda r: flt(r["panel_capacity_kw"]))
	if not rows:
		return None
	for row in rows:
		if flt(row["panel_capacity_kw"]) >= capacity - 0.001:
			return row["bom"]
	return rows[-1]["bom"]


@frappe.whitelist()
def bom_items(bom):
	"""A structure BOM's lines, as the task shows them, and what the BOM is for."""
	if not bom:
		return {"bom": None, "lines": []}
	if not frappe.db.exists("BOM", bom):
		frappe.throw(_("BOM {0} does not exist.").format(bom), frappe.DoesNotExistError)
	head = frappe.db.get_value("BOM", bom, ["name", "item", "item_name", "quantity", "is_active"], as_dict=True)
	items = frappe.get_all(
		"BOM Item", filters={"parent": bom, "parenttype": "BOM"},
		fields=["item_code", "item_name", "description", "qty", "uom"], order_by="idx asc",
	)
	return {
		"bom": head.name,
		"title": head.item_name or head.item,
		"active": bool(head.is_active),
		# `lines`, not `items`: a template reads `x.items` as the dict's own method.
		"lines": [{
			"item_code": r.item_code, "item_name": r.item_name or r.item_code,
			"description": frappe.utils.strip_html(r.description or "") if (r.description or "") != (r.item_name or "") else "",
			"qty": flt(r.qty), "uom": r.uom,
		} for r in items],
	}


def choices_for(doc):
	"""The structure BOMs a task can choose from: its project's package's, labelled by roof
	type and capacity - the package's list, whoever may read ERPNext's BOMs."""
	inst = doc.get("solar_installation") if doc else None
	package = frappe.db.get_value("Solar Installation", inst, "solar_package") if inst else None
	if not package:
		return []
	rows = frappe.get_all(
		"Solar Package Structure BOM", filters={"parent": package, "parenttype": "Solar Package"},
		fields=["roof_type", "panel_capacity_kw", "bom"], order_by="roof_type asc, panel_capacity_kw asc",
	)
	roofs = dict(frappe.get_all("Roof Type", fields=["name", "roof_type"], as_list=True))
	return [{
		"value": r.bom,
		"label": "{0} · {1:g} kW · {2}".format(roofs.get(r.roof_type) or r.roof_type, flt(r.panel_capacity_kw), r.bom),
	} for r in rows if r.bom]


#: The material list each procurement task keeps, and the BOM field it is filled from.
MATERIAL_LISTS = {"SPROC": ("structure_materials", "structure_bom"), "PROC": ("materials", "material_bom")}


def fill_materials(task):
	"""A procurement task's material list, from its BOM's lines."""
	table, bom_field = MATERIAL_LISTS[task.task_code]
	task.set(table, [])
	for line in bom_items(task.get(bom_field))["lines"]:
		task.append(table, {
			"material": line["item_name"], "qty": line["qty"], "uom": line["uom"], "item_code": line["item_code"],
		})


def match_items(rows):
	"""Name the ERPNext item of each line that has none, where a material is an item by name
	- lines edited on the portal come back without the read-only code."""
	wanted = {r.material for r in rows if r.material and not r.item_code}
	if not wanted:
		return
	codes = dict(frappe.get_all("Item", filters={"item_name": ["in", list(wanted)], "disabled": 0},
		fields=["item_name", "name"], as_list=True))
	for r in rows:
		if not r.item_code and r.material in codes:
			r.item_code = codes[r.material]


def material_choices_for(doc):
	"""The material BOM a task can choose: its project's package's."""
	inst = doc.get("solar_installation") if doc else None
	package = frappe.db.get_value("Solar Installation", inst, "solar_package") if inst else None
	bom = frappe.db.get_value("Solar Package", package, "bom") if package else None
	if not bom:
		return []
	title = frappe.db.get_value("BOM", bom, "item_name") or bom
	return [{"value": bom, "label": f"{title} · {bom}"}]

