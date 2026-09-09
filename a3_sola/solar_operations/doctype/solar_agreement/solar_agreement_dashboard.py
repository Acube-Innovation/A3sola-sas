# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: the agreement sits between the stamp paper and commissioning, so
# the chain must be walkable in both directions from here.


from frappe import _


def get_data():
	return {
		"fieldname": "solar_installation",
		"non_standard_fieldnames": {
			"Solar Design Estimate": "solar_consumer",
			"Site Survey": "solar_consumer",
		},
		"transactions": [
			{
				"label": _("Chain"),
				"items": ["Solar Installation", "Commissioning Report"],
			},
			{
				"label": _("Origin"),
				"items": ["Site Survey", "Solar Design Estimate"],
			},
		],
	}
