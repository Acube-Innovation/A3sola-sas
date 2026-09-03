# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Solar Consumer, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "solar_consumer",
		"transactions": [
			{
				"label": _("Assessment"),
				"items": ["Site Survey", "Solar Design Estimate", "Subsidy Eligibility Check"],
			},
			{
				"label": _("Sales"),
				"items": ["Solar Proposal", "Quotation", "Sales Order"],
			},
			{
				"label": _("Execution"),
				"items": ["Solar Installation", "Installation Work Order", "Commissioning Report"],
			},
			{
				"label": _("Statutory"),
				"items": ["Portal Application", "Statutory Fee Payment", "Net Metering Agreement"],
			},
			{
				"label": _("Funding"),
				"items": ["Subsidy Claim", "Loan Application"],
			},
			{
				"label": _("Delivery"),
				"items": ["Project", "Solar OM Contract"],
			},
		],
	}
