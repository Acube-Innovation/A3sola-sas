# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A project's structure bill of materials - the pipes, consumables, bolts and caps the
mounting structure is built from.

Each Solar Package lists its structure BOMs (ERPNext BOMs) by roof type and panel capacity.
A project takes the one for its own roof type at its capacity, else the next larger one -
a structure built for more panels carries fewer - else the largest there is. A BOM frozen
for the project in its Design Freeze task (Solar Installation.structure_bom, .material_bom)
comes before the package's, for the structure and for the system alike.

The system's material BOM follows the inverter, not the package: A3 Sola Settings lists one per
inverter phase and capacity (Inverter Capacity BOM), picked as the structure's is, and the job's
own panels - make, Wp and count from its design - are added to its lines.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt


def bom_for(installation):
	"""The structure BOM for a project (a Solar Installation, or its name), or None."""
	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	if inst.get("structure_bom"):
		return inst.structure_bom
	if not (inst.get("solar_package") and inst.get("roof_type")):
		return None
	rows = frappe.get_all(
		"Solar Package Structure BOM",
		filters={"parent": inst.solar_package, "parenttype": "Solar Package", "roof_type": inst.roof_type},
		fields=["panel_capacity_kw", "bom"], order_by="panel_capacity_kw asc",
	)
	return pick(rows, flt(inst.get("capacity_kw")))


def material_bom_for(installation):
	"""The system's BOM for a project: the one frozen for it, else the one for its inverter's
	capacity, else its package's."""
	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	if inst.get("material_bom"):
		return inst.material_bom
	return capacity_bom_for(inst) or (
		frappe.db.get_value("Solar Package", inst.solar_package, "bom") if inst.get("solar_package") else None)


def job_inverter(inst):
	"""The project's inverter: its phase and total kW, from the chosen inverter row of its design."""
	row = next((r for r in inst.get("inverters") or [] if not r.is_option), None)
	kw = flt(row.inverter_capacity_kw) * (cint(row.nos) or cint(row.inverter_count) or 1) if row else 0
	return (row and row.inverter_phase) or inst.get("connection_type"), kw or flt(inst.get("inverter_capacity_kw"))


def capacity_bom_for(inst):
	"""The material BOM for the project's inverter phase and capacity, from A3 Sola Settings."""
	phase, kw = job_inverter(inst)
	if not (phase and kw):
		return None
	rows = frappe.get_all("Inverter Capacity BOM", filters={"parenttype": "A3 Sola Settings", "inverter_phase": phase},
		fields=["inverter_capacity_kw as panel_capacity_kw", "bom"])
	return pick(rows, kw)


def capacity_boms():
	"""Every BOM A3 Sola Settings lists by inverter capacity."""
	return set(frappe.get_all("Inverter Capacity BOM", filters={"parenttype": "A3 Sola Settings"}, pluck="bom"))


def panel_lines(inst):
	"""The project's panels as BOM lines: each chosen panel row of its design, on the module Item
	of its make and Wp - or, with none on the Item master, a line naming it to be picked."""
	lines = []
	for row in inst.get("panels") or []:
		count = cint(row.panel_count) or cint(row.nos)
		if row.is_option or not (count and row.panel_capacity_wp):
			continue
		make = frappe.db.get_value("Component Make", row.panel_make, "make_name") if row.panel_make else ""
		item = panel_item(make, flt(row.panel_capacity_wp), row.panel_type != "Non-DCR")
		name = frappe.db.get_value("Item", item, "item_name") if item else "{0} {1:g} Wp {2} Module".format(
			make or "", flt(row.panel_capacity_wp), row.panel_type or "").strip()
		lines.append({"item_code": item or "", "item_name": name, "description": "", "qty": count, "uom": "Nos",
			"note": "" if item else _("No module Item for this make and Wp: choose one.")})
	return lines


def panel_item(make, wp, dcr=True):
	"""The module Item of a make and Wp: brand the make (without "Non-DCR"), name carrying the Wp,
	its DCR flag the panel's when both exist."""
	brand = (make or "").replace("Non-DCR", "").strip()
	if not brand:
		return None
	filters = {"brand": brand, "disabled": 0, "item_name": ["like", "%{0:g} Wp%".format(wp)]}
	if frappe.db.exists("Item Group", "Modules"):
		lft, rgt = frappe.db.get_value("Item Group", "Modules", ["lft", "rgt"])
		filters["item_group"] = ["in", frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")]
	found = frappe.get_all("Item", filters=filters, fields=["name", "is_dcr"] if frappe.db.has_column("Item", "is_dcr") else ["name"],
		order_by="name asc")
	return next((f.name for f in found if bool(f.get("is_dcr")) == dcr), None) or (found[0].name if found else None)


def structure_boms():
	"""Every BOM some package lists as a structure BOM."""
	return set(frappe.get_all("Solar Package Structure BOM", filters={"parenttype": "Solar Package"}, pluck="bom"))


def job_boms():
	"""Every BOM a project holds that no package lists - a job's own, edited in its Design
	Freeze; it is offered to that job only."""
	held = set()
	for field in ("material_bom", "structure_bom"):
		held |= set(frappe.get_all("Solar Installation", filters={field: ["is", "set"]}, pluck=field))
	return held - structure_boms() - set(frappe.get_all("Solar Package", filters={"bom": ["is", "set"]}, pluck="bom"))


def _label(bom):
	return "{0} · {1}".format(frappe.db.get_value("BOM", bom, "item_name") or bom, bom)


def _with(choices, *boms):
	"""`choices` with each of `boms` it lacks put first - the one a record holds is always offered."""
	have = {c["value"] for c in choices}
	extra = [{"value": b, "label": _label(b)} for b in boms if b and b not in have]
	return extra + choices


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
def bom_items(bom, installation=None):
	"""A BOM's lines, as the task shows them, and what the BOM is for. For a project whose
	inverter is a micro inverter, the DCDB line is 0 - it has none (api/microinverter.py);
	the BOM itself, shared with string jobs, is left as it is."""
	from a3_sola.api import microinverter

	if not bom:
		return {"bom": None, "lines": []}
	if not frappe.db.exists("BOM", bom):
		frappe.throw(_("BOM {0} does not exist.").format(bom), frappe.DoesNotExistError)
	head = frappe.db.get_value("BOM", bom, ["name", "item", "item_name", "quantity", "is_active"], as_dict=True)
	items = frappe.get_all(
		"BOM Item", filters={"parent": bom, "parenttype": "BOM"},
		fields=["item_code", "item_name", "description", "qty", "uom"], order_by="idx asc",
	)
	micro = bool(installation) and microinverter.uses_microinverter(installation)
	no_dcdb = lambda r: micro and microinverter.is_dcdb(r.item_name or r.item_code)  # noqa: E731
	# A BOM by inverter capacity carries no panels: the job's own are added.
	panels = []
	if installation and bom in capacity_boms():
		inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
		have = {r.item_code for r in items}
		panels = [p for p in panel_lines(inst) if not p["item_code"] or p["item_code"] not in have]
	return {
		"bom": head.name,
		"title": head.item_name or head.item,
		"active": bool(head.is_active),
		# `lines`, not `items`: a template reads `x.items` as the dict's own method.
		"lines": panels + [{
			"item_code": r.item_code, "item_name": r.item_name or r.item_code,
			"description": frappe.utils.strip_html(r.description or "") if (r.description or "") != (r.item_name or "") else "",
			"qty": 0 if no_dcdb(r) else flt(r.qty), "uom": r.uom,
			"note": microinverter.NOTE if no_dcdb(r) else "",
		} for r in items],
	}


def choices_for(doc):
	"""The structure BOMs a task can choose from: its project's package's, labelled by roof
	type and capacity - the package's list, whoever may read ERPNext's BOMs."""
	inst = (doc.get("solar_installation") if doc.doctype != "Solar Installation" else doc.name) if doc else None
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
	for line in bom_items(task.get(bom_field), task.get("solar_installation"))["lines"]:
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
	"""The material BOMs a task or the Design Freeze can choose: the project's frozen one, the one
	for its inverter's capacity and its package's first, then every other active BOM that is not
	a structure BOM."""
	inst = (doc.get("solar_installation") if doc.doctype != "Solar Installation" else doc.name) if doc else None
	project = frappe.get_doc("Solar Installation", inst) if inst else None
	package_bom = frappe.db.get_value("Solar Package", project.solar_package, "bom") if project and project.solar_package else None
	skip = structure_boms() | job_boms()
	others = frappe.get_all("BOM", filters={"is_active": 1, "docstatus": 1}, fields=["name", "item_name"], order_by="item_name asc")
	choices = [{"value": b.name, "label": f"{b.item_name or b.name} · {b.name}"} for b in others if b.name not in skip]
	return _with(choices, project.material_bom if project else None, capacity_bom_for(project) if project else None,
		package_bom, doc.get("material_bom") if doc else None)


def structure_choices_for(doc):
	"""The structure BOMs the Design Freeze can choose: its package's by roof and capacity,
	then every other package's structure BOM, with the project's own always offered."""
	choices = choices_for(doc)
	have = {c["value"] for c in choices}
	choices += [{"value": b, "label": _label(b)} for b in sorted(structure_boms()) if b and b not in have]
	inst = (doc.get("solar_installation") if doc.doctype != "Solar Installation" else doc.name) if doc else None
	return _with(choices, frappe.db.get_value("Solar Installation", inst, "structure_bom") if inst else None,
		doc.get("structure_bom") if doc else None)

