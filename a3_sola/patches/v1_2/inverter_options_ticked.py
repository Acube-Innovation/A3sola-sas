# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Ticked inverter options are part of the system; a recommended one stays chosen.

Options now add up: each ticked option's inverters, and its package's panels, are in the
system, and only a package's default inverter starts ticked. An estimate that recommended
another inverter of its package keeps it - it is ticked in place of the default - and every
draft is saved once so its panel and inverter tables are rebuilt from its options. One
that fails to save is logged and left as it was.
"""

import frappe

from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import package_inverter_alternatives


def execute():
	for name in frappe.get_all("Solar Design Estimate", filters={"docstatus": 0}, pluck="name"):
		doc = frappe.get_doc("Solar Design Estimate", name)
		chosen = next((r for r in doc.options if r.from_package and r.is_recommended and r.solar_package), None)
		if chosen and frappe.db.exists("Solar Package", chosen.solar_package):
			package = frappe.get_doc("Solar Package", chosen.solar_package)
			candidates = package_inverter_alternatives(package, doc.connection_type)
			default = next((r.inverter_make for r in candidates if r.is_default), None) or (
				candidates[0].inverter_make if candidates else None)
			if default and chosen.inverter_make != default:
				included = set(filter(None, (doc.included_inverter_options or "").splitlines()))
				excluded = set(filter(None, (doc.excluded_inverter_makes or "").splitlines()))
				included.add(f"{package.name}|{chosen.inverter_make}")
				excluded.add(f"{package.name}|{default}")
				doc.included_inverter_options = "\n".join(sorted(included))
				doc.excluded_inverter_makes = "\n".join(sorted(excluded))
		try:
			doc.flags.ignore_permissions = True
			doc.save()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"inverter_options_ticked: {name} skipped")
		else:
			frappe.db.commit()
