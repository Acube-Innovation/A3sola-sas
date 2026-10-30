# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One material bill of materials, for an inverter phase and capacity: a job takes the one for
its own inverter (api/structure_bom.py), and its panels beside it."""

from frappe.model.document import Document


class InverterCapacityBOM(Document):
	pass
