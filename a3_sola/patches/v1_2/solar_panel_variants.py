# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The solar panel variants the client sells, DCR and Non-DCR, each at its rate per watt: the
panel's selling price is its Wp times that rate, on the Standard Selling price list, where a
design estimate prices a panel no package covers (api/structure_bom.panel_rate).

Each panel is a module Item - the six already on the Item master keep their codes - and each
brand, DCR status and technology in the list has a Component Make, so the panel can be chosen
on an estimate. A price already there is updated to the list's.

The data ships in `a3_sola/data/solar_panel_variants.json`."""

import json
import os

import frappe
from frappe.utils import flt

from a3_sola.patches.v1_2.package_material_boms import ensure_item

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "solar_panel_variants.json")
SELLING = "Standard Selling"
GROUPS = {"TOPCon Bifacial": "TOPCon Modules", "Mono PERC Bifacial": "Mono PERC Modules"}
SHORT = {"TOPCon Bifacial": "TOPCon", "Mono PERC Bifacial": "Mono PERC"}


def execute():
	panels = json.load(open(DATA, encoding="utf-8"))["panels"]
	if not frappe.db.exists("Price List", SELLING):
		frappe.get_doc({"doctype": "Price List", "price_list_name": SELLING, "selling": 1,
			"currency": "INR"}).insert(ignore_permissions=True)
	company = frappe.db.get_value("Component Make", {"component_type": "Module"}, "company") \
		or frappe.db.get_single_value("Global Defaults", "default_company")
	makes = []
	for p in panels:
		ensure_item({
			"item_code": p["item_code"], "item_name": p["item_name"],
			"item_group": GROUPS[p["technology"]] if frappe.db.exists("Item Group", GROUPS[p["technology"]]) else "All Item Groups",
			"stock_uom": "Nos", "is_stock_item": 1, "has_serial_no": 1, "brand": p["brand"],
			"description": "{0} - {1}".format(p["item_name"], p["series"]), "disabled": 0,
			"is_dcr": p["is_dcr"], "dcr_certificate_no": None, "gst_hsn_code": "85414300", "purchase_rate": None,
		})
		set_selling_price(p)
		make = ensure_make(p, company)
		if make:
			makes.append(make)
	frappe.db.commit()
	if makes:
		print("Component Makes added: " + ", ".join(makes))


def set_selling_price(p):
	note = "{0:g} ₹/W x {1:g} Wp".format(p["rate_per_watt"], p["wp"])
	name = frappe.db.get_value("Item Price", {"item_code": p["item_code"], "price_list": SELLING})
	if name:
		if flt(frappe.db.get_value("Item Price", name, "price_list_rate")) != flt(p["rate"]):
			frappe.db.set_value("Item Price", name, {"price_list_rate": p["rate"], "note": note})
		return
	frappe.get_doc({"doctype": "Item Price", "item_code": p["item_code"], "price_list": SELLING, "uom": "Nos",
		"price_list_rate": p["rate"], "note": note}).insert(ignore_permissions=True)


def technology(name, company):
	found = frappe.db.get_value("Component Technology", {"technology_name": name, "component_type": "Module"})
	if found:
		return found
	return frappe.get_doc({"doctype": "Component Technology", "technology_name": name, "component_type": "Module",
		"is_active": 1, "company": company}).insert(ignore_permissions=True).name


def ensure_make(p, company):
	"""A Component Make for the panel's brand, DCR status and technology, unless one exists.
	Returns the make name created, if any."""
	tech = technology(p["technology"], company)
	base = p["brand"] + ("" if p["is_dcr"] else " Non-DCR")
	if frappe.db.exists("Component Make", {"component_type": "Module", "is_dcr": p["is_dcr"], "technology": tech,
			"make_name": ["like", p["brand"] + "%"]}):
		return None
	name = base if not frappe.db.exists("Component Make", {"make_name": base, "component_type": "Module"}) \
		else "{0} {1}".format(base, SHORT[p["technology"]])
	frappe.get_doc({"doctype": "Component Make", "make_name": name, "component_type": "Module", "technology": tech,
		"is_dcr": p["is_dcr"], "is_active": 1, "company": company}).insert(ignore_permissions=True)
	return name
