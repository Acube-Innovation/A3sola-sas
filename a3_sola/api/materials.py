# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Material flow against an installation.

Every movement is attributable to a job, so Phase 3 can cost it and the site can be
reconciled against the package BOM.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api.settings import get_float, get_value


@frappe.whitelist()
def get_installation_material_summary(installation):
	"""Per item: BOM required, requested, received at site, consumed, returned, variance."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("read")

	required = _bom_requirement(doc)
	requested = _sum_child("Material Request Item", "Material Request", doc, "qty")
	received = _sum_child("Stock Entry Detail", "Stock Entry", doc, "qty")
	delivered = _sum_child("Delivery Note Item", "Delivery Note", doc, "qty")

	items = set(required) | set(requested) | set(received) | set(delivered)
	rows = []
	for item in sorted(items):
		bom_qty = flt(required.get(item))
		consumed = flt(delivered.get(item)) or flt(received.get(item))
		variance = consumed - bom_qty
		rows.append(
			{
				"item": item,
				"item_name": frappe.db.get_value("Item", item, "item_name"),
				"bom_required": bom_qty,
				"requested": flt(requested.get(item)),
				"received_at_site": flt(received.get(item)),
				"consumed": consumed,
				"variance": variance,
				"variance_percent": flt(variance * 100.0 / bom_qty, 2) if bom_qty else 0.0,
			}
		)
	return rows


def _bom_requirement(installation):
	"""Explode the package BOM to the installed capacity."""
	if not installation.solar_package:
		return {}
	package = frappe.get_cached_doc("Solar Package", installation.solar_package)
	if not package.bom:
		return {
			row.item: flt(row.qty)
			for row in package.components
			if row.item and flt(row.qty)
		}
	scale = flt(installation.capacity_kw) / flt(package.capacity_kw) if flt(package.capacity_kw) else 1.0
	return {
		row.item_code: flt(row.qty) * scale
		for row in frappe.get_all("BOM Item", filters={"parent": package.bom}, fields=["item_code", "qty"])
	}


def _sum_child(child_doctype, parent_doctype, installation, qty_field):
	parents = frappe.get_all(
		parent_doctype,
		filters={"solar_installation": installation.name, "docstatus": 1},
		pluck="name",
	)
	if not parents:
		return {}
	totals = {}
	for row in frappe.get_all(
		child_doctype,
		filters={"parent": ["in", parents]},
		fields=["item_code", qty_field],
	):
		totals[row.item_code] = totals.get(row.item_code, 0) + flt(row.get(qty_field))
	return totals


@frappe.whitelist()
def create_material_request(installation):
	"""Material Transfer request from the package BOM, exploded to installed capacity."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")

	required = _bom_requirement(doc)
	if not required:
		frappe.throw(_("Package {0} has no BOM or component list to request from.").format(doc.solar_package))

	source = get_value("default_source_warehouse")
	target = get_value("site_warehouse_group")
	request = frappe.get_doc(
		{
			"doctype": "Material Request",
			"company": doc.company,
			"material_request_type": "Material Transfer",
			"transaction_date": frappe.utils.today(),
			"schedule_date": frappe.utils.add_days(frappe.utils.today(), 7),
			"solar_installation": doc.name,
			"items": [
				{
					"item_code": item,
					"qty": qty,
					"schedule_date": frappe.utils.add_days(frappe.utils.today(), 7),
					"warehouse": target,
					"from_warehouse": source,
				}
				for item, qty in required.items()
			],
		}
	)
	request.flags.ignore_permissions = True
	request.insert(ignore_permissions=True)
	return request.name


def check_variance(installation):
	"""Warn - never block - when consumption deviates beyond tolerance at commissioning."""
	tolerance = get_float("material_variance_tolerance_percent", 5.0)
	over = [
		row
		for row in get_installation_material_summary(installation.name)
		if row["bom_required"] and abs(row["variance_percent"]) > tolerance
	]
	if not over:
		return []
	frappe.msgprint(
		_("Material consumption deviates beyond {0}% on {1} item(s): {2}. Record a remark explaining why.").format(
			tolerance, len(over), ", ".join(r["item"] for r in over[:5])
		),
		title=_("Material Variance"),
		indicator="orange",
	)
	return over
