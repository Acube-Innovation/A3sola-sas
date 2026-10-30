# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The structure BOM follows the roof and the panel capacity: the client's lists for a 3 kW and a
5 kW flat roof and a 5 kW sheet roof, listed in A3 Sola Settings, where every job finds them.

The sheet roof BOM put on the 3kW and 5kW System packages earlier (30-Oct-2026) is retired: the
packages drop it, jobs whose design is not yet frozen drop it, and draft procurement tasks are
refilled. A frozen design or a submitted task keeps the BOM it was made with.

The data ships in `a3_sola/data/panel_capacity_structure_boms.json`."""

import json
import os

import frappe
from frappe.utils import flt

from a3_sola.patches.v1_2.package_material_boms import ensure_item, make_bom

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "panel_capacity_structure_boms.json")
SETTINGS = "A3 Sola Settings"
#: The package sheet roof BOM it replaces, by the item it was made for.
RETIRED_ITEM = "MNT-STRUCT-SHEET-ROOF"


def execute():
	frappe.reload_doc("solar_crm", "doctype", "panel_capacity_structure_bom")
	frappe.reload_doc("solar_crm", "doctype", "a3_sola_settings")
	data = json.load(open(DATA, encoding="utf-8"))
	for uom in data["uoms"]:
		if not frappe.db.exists("UOM", uom):
			frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
	for item in data["items"]:
		ensure_item(item)

	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {})
	settings = frappe.get_single(SETTINGS)
	skipped, added = [], False
	for spec in data["templates"]:
		roof = frappe.db.get_value("Roof Type", {"roof_type": spec["roof_type"]})
		if not roof:
			skipped.append(f"{spec['item']}: no Roof Type '{spec['roof_type']}'")
			continue
		if any(r.roof_type == roof and flt(r.panel_capacity_kw) == spec["panel_capacity_kw"]
				for r in settings.get("structure_boms") or []):
			continue
		bom = frappe.db.get_value("BOM", {"item": spec["item"], "docstatus": 1, "is_active": 1}) or make_bom({
			"item": spec["item"],
			"items": [[code, qty, frappe.db.get_value("Item", code, "stock_uom")] for code, qty in spec["items"]],
		}, company)
		settings.append("structure_boms", {"roof_type": roof, "panel_capacity_kw": spec["panel_capacity_kw"], "bom": bom,
			"remarks": "From the client's list: {0}".format(spec["source"])})
		added = True
	if added:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save()
	frappe.db.commit()
	retire_package_sheet_roof()
	if skipped:
		print("Structure BOMs not set:\n  " + "\n  ".join(skipped))


def retire_package_sheet_roof():
	from a3_sola.api.design_freeze import refresh_procurement

	old = frappe.get_all("BOM", filters={"item": RETIRED_ITEM, "docstatus": 1, "is_active": 1}, pluck="name")
	if not old:
		return
	for name in frappe.get_all("Solar Package Structure BOM", filters={"bom": ["in", old], "parenttype": "Solar Package"},
			pluck="parent"):
		package = frappe.get_doc("Solar Package", name)
		package.set("structure_boms", [r for r in package.structure_boms if r.bom not in old])
		package.flags.ignore_links = True
		package.save(ignore_permissions=True)
	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		frozen = any(r.stage_code in ("DSGN", "SDSGN") and r.status == "Completed" for r in inst.stages)
		if inst.get("structure_bom") in old and not frozen:
			frappe.db.set_value("Solar Installation", name, "structure_bom", None, update_modified=False)
			inst.structure_bom = None
		refresh_procurement(inst)
	for name in old:
		frappe.db.set_value("BOM", name, {"is_active": 0, "is_default": 0})
	if frappe.db.get_value("Item", RETIRED_ITEM, "default_bom") in old:
		frappe.db.set_value("Item", RETIRED_ITEM, "default_bom", None)
	frappe.db.commit()
	print("Package structure BOMs retired: " + ", ".join(old))
