# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Inverters come from the master price list: seed its models, put each package inverter row
on the model it is - same make and phase, the same kW or the next up within 10% (a 3 kW
Solinteg row is the OGS-3.3K) - and reprice the packages and draft estimates on them.
A SolarEdge row is with its optimizers: that is how its package was priced."""

import frappe
from frappe.utils import cint, flt

from a3_sola.setup.inverter_models import seed_inverter_models
from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import model_values


def execute():
	for doctype in ("inverter_model", "solar_package_inverter", "design_estimate_inverter"):
		frappe.reload_doc("solar_crm", "doctype", doctype)
	for company in frappe.get_all("Company", pluck="name"):
		if frappe.db.exists("Component Make", {"company": company, "component_type": "Inverter"}):
			seed_inverter_models(company)

	unmatched = []
	for name in frappe.get_all("Solar Package", pluck="name"):
		package = frappe.get_doc("Solar Package", name)
		for row in package.get("inverters") or []:
			if row.get("inverter_model"):
				continue
			row.inverter_model = match(row, package.connection_type)
			if not row.inverter_model:
				unmatched.append(f"{name}: {row.inverter_specification}")
				continue
			row.with_optimizer = 1 if frappe.db.get_value("Inverter Model", row.inverter_model, "optimizer_model") else 0
		package.flags.ignore_links = True
		package.save(ignore_permissions=True)

	for name in frappe.get_all("Solar Design Estimate", filters={"docstatus": 0}, pluck="name"):
		doc = frappe.get_doc("Solar Design Estimate", name)
		if not doc.solar_package:
			continue
		# Each package inverter row takes its package row's model; nothing else on it changes.
		for row in doc.get("inverters") or []:
			if row.get("inverter_model") or not row.in_package:
				continue
			package_name = (row.option_key or "").split("|")[0] or doc.solar_package
			source = next((r for r in frappe.get_cached_doc("Solar Package", package_name).get("inverters") or []
				if r.inverter_make == row.inverter_make and r.get("inverter_model")
				and flt(r.inverter_capacity_kw) * (cint(r.inverter_count) or 1)
				== flt(row.inverter_capacity_kw) * (cint(row.inverter_count) or 1)), None) \
				if frappe.db.exists("Solar Package", package_name) else None
			if source:
				row.update(model_values(source))
		doc.flags.ignore_links = True
		try:
			doc.save(ignore_permissions=True)
		except frappe.ValidationError:
			frappe.db.rollback()
			unmatched.append(f"{name}: not re-saved")
		frappe.db.commit()
	if unmatched:
		print("Inverter rows left without a model:\n  " + "\n  ".join(unmatched))


def match(row, connection_type):
	"""The model for a package row: same make and phase, its whole kW (a 3 x 1 kW micro row is
	the 3 kW kit), else the next model up within 10%."""
	kw = flt(flt(row.inverter_capacity_kw) * (cint(row.inverter_count) or 1), 3)
	models = frappe.get_all("Inverter Model",
		filters={"inverter_make": row.inverter_make, "inverter_phase": row.inverter_phase or connection_type, "is_active": 1},
		fields=["name", "capacity_kw"], order_by="capacity_kw")
	return next((m.name for m in models if flt(m.capacity_kw) == kw), None) or next(
		(m.name for m in models if kw < flt(m.capacity_kw) <= kw * 1.1), None)
