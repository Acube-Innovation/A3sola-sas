# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Delivery Note: guard serial uniqueness at the point of dispatch.

Catching a duplicate serial here, rather than at portal submission weeks later, is the
difference between a five-minute correction and a rejected claim.
"""

import frappe

from a3_sola.api import documents, serials


def on_submit(doc, method=None):
	if not doc.get("solar_installation"):
		return
	for item in doc.items:
		for serial in (item.serial_no or "").split("\n"):
			serial = serial.strip()
			if serial:
				serials.validate_serial_uniqueness(serial, doc.solar_installation, doc.company)
	# The dispatch is the job's serial capture: what left the store is what is on the roof.
	try:
		serials.pull_serials_from_delivery_note(doc.solar_installation)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: serial pull from {doc.name}")
	try:
		documents.register_print(doc, doc.solar_installation, "Delivery note", "DISP")
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: register delivery note {doc.name}")
