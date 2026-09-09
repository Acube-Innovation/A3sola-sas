# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	return {
		"fieldname": "solar_contractor",
		"transactions": [
			{"label": _("Work"), "items": ["Installation Work Order", "Material Dispatch Notice"]},
			{"label": _("Certificates"), "items": ["Installation Task"]},
		],
	}
