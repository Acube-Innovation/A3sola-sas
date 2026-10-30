# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One structure bill of materials, for a roof type and panel capacity: a job takes the one for
its own roof and size (api/structure_bom.py) when its package lists none."""

from frappe.model.document import Document


class PanelCapacityStructureBOM(Document):
	pass
