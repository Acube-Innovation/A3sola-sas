# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Delivery Note: guard serial uniqueness at the point of dispatch.

Catching a duplicate serial here, rather than at portal submission weeks later, is the
difference between a five-minute correction and a rejected claim.
"""

import frappe

from a3_sola.api import serials


def on_submit(doc, method=None):
	if not doc.get("solar_installation"):
		return
	for item in doc.items:
		for serial in (item.serial_no or "").split("\n"):
			serial = serial.strip()
			if serial:
				serials.validate_serial_uniqueness(serial, doc.solar_installation, doc.company)
