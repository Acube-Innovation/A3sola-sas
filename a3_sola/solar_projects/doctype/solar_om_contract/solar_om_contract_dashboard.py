# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt


def get_data():
	return {
		"fieldname": "om_contract",
		"non_standard_fieldnames": {
			"Project": "name",
			"Generation Reading": "om_contract",
		},
		"transactions": [
			{"label": "Service", "items": ["Solar OM Visit", "Service Ticket"]},
			{"label": "Performance", "items": ["Generation Reading"]},
			{"label": "Warranty", "items": ["Solar Warranty Claim"]},
		],
	}
