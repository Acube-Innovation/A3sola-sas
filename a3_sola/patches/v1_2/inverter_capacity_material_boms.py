# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The material BOM follows the inverter: one per inverter phase and capacity, from the client's
material list (3 kW and 5 kW single phase, 8 kW three phase), listed in A3 Sola Settings. The
job's panels are added from its design, so the BOMs carry none.

The package BOMs they replace (3kW and 5kW System, 30-Oct-2026) are unlinked and set inactive:
packages drop them, jobs not yet frozen drop them, and draft procurement tasks are refilled. A
completed freeze or a submitted task keeps the BOM it was made with.

The data ships in `a3_sola/data/inverter_capacity_boms.json`."""

import json
import os

import frappe

from a3_sola.patches.v1_2.package_material_boms import ensure_item, make_bom

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "inverter_capacity_boms.json")
SETTINGS = "A3 Sola Settings"
#: The package BOMs of 30-Oct-2026, by the package item they were made for.
RETIRED_ITEMS = ("PMSG 3KW SYSTEM 1PH", "PMSG 5KW SYSTEM 1PH")


def execute():
	frappe.reload_doc("solar_crm", "doctype", "inverter_capacity_bom")
	frappe.reload_doc("solar_crm", "doctype", "a3_sola_settings")
	add_templates(json.load(open(DATA, encoding="utf-8")))
	retire_package_boms()


def add_templates(data):
	"""Create the data's items and its BOMs by inverter capacity, and list each in A3 Sola Settings
	where no row has its phase and capacity yet."""
	if not frappe.db.exists("Item Group", "Sub Assemblies"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "Sub Assemblies",
			"parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
	for item in data["items"]:
		ensure_item(item)

	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {})
	settings = frappe.get_single(SETTINGS)
	added = False
	for spec in data["templates"]:
		have = next((r for r in settings.get("material_boms") or [] if r.inverter_phase == spec["inverter_phase"]
			and frappe.utils.flt(r.inverter_capacity_kw) == spec["inverter_capacity_kw"]), None)
		if have:
			continue
		bom = frappe.db.get_value("BOM", {"item": spec["item"], "docstatus": 1, "is_active": 1}) or make_bom({
			"item": spec["item"],
			"items": [[code, qty, frappe.db.get_value("Item", code, "stock_uom")] for code, qty in spec["items"]],
		}, company)
		settings.append("material_boms", {"inverter_phase": spec["inverter_phase"],
			"inverter_capacity_kw": spec["inverter_capacity_kw"], "bom": bom,
			"remarks": "From the material list of {0}'s job".format(spec["source"])})
		added = True
	if added:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save()
	frappe.db.commit()


def retire_package_boms():
	from a3_sola.api.design_freeze import refresh_procurement

	old = frappe.get_all("BOM", filters={"item": ["in", RETIRED_ITEMS], "docstatus": 1}, pluck="name")
	if not old:
		return
	for name in frappe.get_all("Solar Package", filters={"bom": ["in", old]}, pluck="name"):
		frappe.db.set_value("Solar Package", name, "bom", None, update_modified=False)
	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		frozen = next((r for r in inst.stages if r.stage_code == "DSGN" and r.status == "Completed"), None)
		if inst.get("material_bom") in old and not frozen:
			frappe.db.set_value("Solar Installation", name, "material_bom", None, update_modified=False)
			inst.material_bom = None
		refresh_procurement(inst)
	for name in old:
		frappe.db.set_value("BOM", name, {"is_active": 0, "is_default": 0})
	for item in RETIRED_ITEMS:
		if frappe.db.get_value("Item", item, "default_bom") in old:
			frappe.db.set_value("Item", item, "default_bom", None)
	frappe.db.commit()
	print("Package BOMs retired: " + ", ".join(old))
