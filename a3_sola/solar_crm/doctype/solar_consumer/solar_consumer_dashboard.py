# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt


def get_data():
	return {
		"fieldname": "solar_consumer",
		"non_standard_fieldnames": {
			"Quotation": "solar_consumer",
			"Sales Order": "solar_consumer",
			"Opportunity": "solar_consumer",
			"Lead": "solar_consumer",
		},
		"transactions": [
			{"label": "Assessment", "items": ["Site Survey", "Solar Design Estimate", "Subsidy Eligibility Check"]},
			{"label": "Sales", "items": ["Solar Proposal", "Quotation", "Sales Order"]},
		],
	}
