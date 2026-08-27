# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cost Overrun Analysis.

Rework is the column to read first: it is the only cost here that the business could have
avoided entirely, and it is deliberately kept out of the labour figure so it stays visible.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Project"), "fieldname": "name", "fieldtype": "Link", "options": "Project", "width": 150},
		{"label": _("kWp"), "fieldname": "capacity_kw", "fieldtype": "Float", "precision": 2, "width": 80},
		{"label": _("Material"), "fieldname": "material_cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Labour"), "fieldname": "labour_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("Subcontractor"), "fieldname": "subcontractor_cost", "fieldtype": "Currency", "width": 130},
		{"label": _("Logistics"), "fieldname": "logistics_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("Liaison"), "fieldname": "liaison_and_statutory_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("Rework"), "fieldname": "rework_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("O&M to Date"), "fieldname": "om_cost_to_date", "fieldtype": "Currency", "width": 120},
		{"label": _("Total Cost"), "fieldname": "total_cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Rework % of Cost"), "fieldname": "rework_share", "fieldtype": "Percent", "width": 140},
		{"label": _("BOM Material"), "fieldname": "bom_material_cost", "fieldtype": "Currency", "width": 130},
		{"label": _("Material Variance"), "fieldname": "material_variance", "fieldtype": "Currency", "width": 150},
		{"label": _("Quoted Value"), "fieldname": "quoted_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Cost as % of Quote"), "fieldname": "cost_of_quote_percent", "fieldtype": "Percent", "width": 160},
		{"label": _("Margin Variance %"), "fieldname": "margin_variance_percent", "fieldtype": "Percent", "width": 150},
	]


def get_data(filters):
	rows = frappe.get_list(
		"Project",
		filters={"company": filters.company, "solar_installation": ["is", "set"]},
		fields=[
			"name", "capacity_kw", "solar_installation", "solar_package", "material_cost",
			"labour_cost", "subcontractor_cost", "logistics_cost",
			"liaison_and_statutory_cost", "rework_cost", "om_cost_to_date", "total_cost",
			"gross_contract_value", "margin_variance_percent",
		],
		limit_page_length=0,
	)
	for row in rows:
		row["rework_share"] = (
			flt(flt(row.rework_cost) * 100.0 / flt(row.total_cost), 2) if flt(row.total_cost) else 0.0
		)

		# What the bill of materials said the kit should cost, against what was issued.
		# Blank until the client links a BOM to the package - the seeded packages ship
		# without one because their pricing is commercially sensitive.
		row["bom_material_cost"] = _bom_cost(row.solar_package)
		row["material_variance"] = (
			flt(flt(row.material_cost) - row["bom_material_cost"], 2)
			if row["bom_material_cost"]
			else 0.0
		)

		row["quoted_value"] = _quoted_value(row)
		row["cost_of_quote_percent"] = (
			flt(flt(row.total_cost) * 100.0 / row["quoted_value"], 2)
			if row["quoted_value"]
			else 0.0
		)

	rows.sort(key=lambda r: (flt(r["cost_of_quote_percent"]), flt(r["rework_share"])), reverse=True)
	return [row for row in rows if flt(row.total_cost)]


def _bom_cost(package):
	if not package:
		return 0.0
	bom = frappe.db.get_value("Solar Package", package, "bom")
	if not bom or not frappe.db.exists("BOM", bom):
		return 0.0
	return flt(frappe.db.get_value("BOM", bom, "total_cost"), 2)


def _quoted_value(row):
	"""What sales put in front of the customer, before any negotiation."""
	estimate = frappe.db.get_value(
		"Solar Installation", row.solar_installation, "solar_design_estimate"
	)
	if estimate:
		quoted = flt(frappe.db.get_value("Solar Design Estimate", estimate, "total_project_cost"))
		if quoted:
			return flt(quoted, 2)
	return flt(row.gross_contract_value, 2)
