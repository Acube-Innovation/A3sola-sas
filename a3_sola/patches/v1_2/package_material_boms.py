# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Material BOMs of the 1 phase 3 kW and 5 kW packages, from the Suryavamshi purchase list
of 08.09.2026, and the RIM Projects item master they are made of.

The data ships in `a3_sola/data/package_material_boms.json`. Groups, items and buying prices
are created only where missing - nothing a user has already edited is overwritten - and a
package that already names a BOM keeps it. Item purchase rates go on the Standard Buying price
list, which the BOMs are costed from; items with no rate yet cost at 0 until one is entered."""

import json
import os

import frappe
from frappe.utils import flt

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "package_material_boms.json")
BUYING = "Standard Buying"


def execute():
	data = json.load(open(DATA, encoding="utf-8"))
	if not frappe.db.exists("UOM", "Bag"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Bag"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Price List", BUYING):
		frappe.get_doc({"doctype": "Price List", "price_list_name": BUYING, "buying": 1,
			"currency": "INR"}).insert(ignore_permissions=True)
	for group in data["item_groups"]:
		ensure_item_group(group)
	for item in data["items"]:
		ensure_item(item)

	skipped = []
	for spec in data["boms"]:
		packages = frappe.get_all("Solar Package", filters={"item": spec["item"]}, fields=["name", "company", "bom"])
		if not packages:
			skipped.append(f"{spec['item']}: no Solar Package sells this item")
		for package in packages:
			if package.bom:
				skipped.append(f"{package.name}: keeps its BOM {package.bom}")
				continue
			bom = make_bom(spec, package.company)
			frappe.db.set_value("Solar Package", package.name, "bom", bom, update_modified=False)
	frappe.db.commit()
	if skipped:
		print("Material BOMs not set:\n  " + "\n  ".join(skipped))


def ensure_item_group(group):
	if frappe.db.exists("Item Group", group["name"]):
		return
	frappe.get_doc({
		"doctype": "Item Group",
		"item_group_name": group["name"],
		"parent_item_group": group["parent"],
		"is_group": group["is_group"],
		"description": group["description"],
	}).insert(ignore_permissions=True)


def ensure_item(spec):
	code = spec["item_code"]
	if not frappe.db.exists("Item", code):
		if spec["brand"] and not frappe.db.exists("Brand", spec["brand"]):
			frappe.get_doc({"doctype": "Brand", "brand": spec["brand"]}).insert(ignore_permissions=True)
		item = frappe.get_doc({
			"doctype": "Item",
			"item_code": code,
			**{k: spec[k] for k in ("item_name", "item_group", "stock_uom", "is_stock_item", "has_serial_no",
				"brand", "description", "disabled")},
			"is_purchase_item": 1,
			"is_sales_item": 0,
		})
		if item.meta.has_field("is_dcr"):
			item.is_dcr = spec["is_dcr"]
			item.dcr_certificate_no = spec["dcr_certificate_no"]
		hsn = item.meta.get_field("gst_hsn_code")
		if hsn and spec["gst_hsn_code"] and (hsn.fieldtype != "Link" or frappe.db.exists(hsn.options, spec["gst_hsn_code"])):
			item.gst_hsn_code = spec["gst_hsn_code"]
		item.insert(ignore_permissions=True)

	if flt(spec["purchase_rate"]) and not frappe.db.exists("Item Price", {"item_code": code, "price_list": BUYING}):
		frappe.get_doc({
			"doctype": "Item Price",
			"item_code": code,
			"price_list": BUYING,
			"uom": spec["stock_uom"],
			"price_list_rate": flt(spec["purchase_rate"]),
		}).insert(ignore_permissions=True)


def make_bom(spec, company):
	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": spec["item"],
		"company": company,
		"quantity": 1,
		"is_active": 1,
		"is_default": 1,
		"rm_cost_as_per": "Price List",
		"buying_price_list": BUYING,
		"items": [{"item_code": code, "qty": flt(qty), "uom": uom} for code, qty, uom in spec["items"]],
	})
	bom.insert(ignore_permissions=True)
	bom.submit()
	return bom.name
