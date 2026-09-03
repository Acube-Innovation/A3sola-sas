# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Solar Installation, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "solar_installation",
		"transactions": [
			{
				"label": _("Execution"),
				"items": ["Installation Work Order", "Installation Snag", "Commissioning Report"],
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
				"items": ["Project", "Solar Billing Plan", "Solar OM Contract"],
			},
			{
				"label": _("Service"),
				"items": ["Solar OM Visit", "Service Ticket", "Solar Warranty Claim", "Generation Reading"],
			},
			{
				"label": _("Accounts"),
				"items": ["Sales Order", "Sales Invoice", "Statutory Fee Recovery"],
			},
		],
	}
