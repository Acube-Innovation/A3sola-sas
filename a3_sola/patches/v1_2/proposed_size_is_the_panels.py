# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A draft estimate's proposed size is the panels designed in (six 550 Wp panels are 3.3 kW),
not the sizing's recommendation: each draft whose size differs is saved again, so its fees,
subsidy and commercials are worked out for it. Submitted estimates stay as they were."""

import frappe
from frappe.utils import flt


def execute():
	for name in frappe.get_all("Solar Design Estimate", filters={"docstatus": 0}, pluck="name"):
		doc = frappe.get_doc("Solar Design Estimate", name)
		panels = doc.panel_capacity_kwp()
		if not panels or flt(panels, 3) == flt(doc.final_capacity_kw, 3):
			continue
		try:
			doc.flags.ignore_permissions = True
			doc.flags.mute_messages = True
			doc.save()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"proposed_size_is_the_panels: {name} skipped")
		else:
			frappe.db.commit()
