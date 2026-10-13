# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Estimates are priced on their package: the package price, plus what is added to it.

A design estimate built on a solar package now charges the package's price-list price for
the configuration it quotes, and shows the package's own panels, inverter, battery, boards,
mounting and installation as included rather than pricing each. Every draft is saved once
so its rows are marked and its commercials follow: package batteries are marked here (they
are not rebuilt on save), and the balance of system is refilled from the package. One that
fails to save is logged and left as it was.
"""

import frappe


def execute():
	for name in frappe.get_all("Solar Design Estimate", filters={"docstatus": 0, "solar_package": ["is", "set"]}, pluck="name"):
		doc = frappe.get_doc("Solar Design Estimate", name)
		if not frappe.db.exists("Solar Package", doc.solar_package):
			continue
		package_batteries = {row.battery_make for row in frappe.get_doc("Solar Package", doc.solar_package).get("batteries") or []}
		for row in doc.get("batteries") or []:
			if row.battery_make in package_batteries:
				row.in_package = 1
		doc.bos_basis = None
		try:
			doc.flags.ignore_permissions = True
			doc.flags.mute_messages = True
			doc.save()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"package_priced_estimates: {name} skipped")
		else:
			frappe.db.commit()
