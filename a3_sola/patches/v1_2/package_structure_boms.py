# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The sheet roof structure BOM - GP tubes, end caps, anchor bolts and the paint and
consumables to put them up - from the 5 kW sheet roof list, on the 1 phase 3 kW and 5 kW
packages for Metal Sheet roofs (the 3 kW package takes the same list until it has its own).

The data ships in `a3_sola/data/package_structure_boms.json`. Items are created only where
missing, and a package that already lists a structure BOM for the roof keeps it. Procurement
tasks saved with an empty material list are then filled from their project's BOMs; a list
someone typed is left as it is."""

import json
import os

import frappe
from frappe.utils import flt

from a3_sola.api.structure_bom import MATERIAL_LISTS
from a3_sola.patches.v1_2.package_material_boms import ensure_item, make_bom

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "package_structure_boms.json")


def execute():
	data = json.load(open(DATA, encoding="utf-8"))
	for uom in data["uoms"]:
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
	for item in data["items"]:
		ensure_item(item)

	skipped = []
	for spec in data["boms"]:
		roof = frappe.db.get_value("Roof Type", {"roof_type": spec["roof_type"]})
		if not roof:
			skipped.append(f"{spec['item']}: no Roof Type '{spec['roof_type']}'")
			continue
		bom = None
		for name in frappe.get_all("Solar Package", filters={"item": ["in", spec["packages"]]}, pluck="name"):
			package = frappe.get_doc("Solar Package", name)
			if any(row.roof_type == roof for row in package.get("structure_boms") or []):
				skipped.append(f"{name}: keeps its {spec['roof_type']} structure BOM")
				continue
			bom = bom or frappe.db.get_value("BOM", {"item": spec["item"], "is_default": 1, "docstatus": 1}) \
				or make_bom(spec, package.company)
			package.append("structure_boms", {"roof_type": roof, "panel_capacity_kw": flt(package.capacity_kw), "bom": bom})
			package.flags.ignore_links = True
			package.save(ignore_permissions=True)
	frappe.db.commit()

	left_empty = []
	for code, (table, _bom_field) in MATERIAL_LISTS.items():
		for name in frappe.get_all("Installation Task", filters={"task_code": code, "docstatus": ["<", 2]}, pluck="name"):
			task = frappe.get_doc("Installation Task", name)
			if task.get(table) or not task.solar_installation:
				continue
			task.pull_structure() if code == "SPROC" else task.pull_material()
			if not task.get(table):
				left_empty.append(f"{name} ({code}): its project has no BOM")
				continue
			task.flags.ignore_validate_update_after_submit = True
			task.flags.ignore_permissions = True
			task.flags.ignore_links = True
			task.save()
	frappe.db.commit()
	if skipped or left_empty:
		print("Structure BOMs not set / task lists left empty:\n  " + "\n  ".join(skipped + left_empty))
