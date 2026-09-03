# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Solar Design Estimate, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "solar_design_estimate",
		"non_standard_fieldnames": {
			"Subsidy Eligibility Check": "design_estimate",
		},
		"transactions": [
			{
				"label": _("Eligibility"),
				"items": ["Subsidy Eligibility Check"],
			},
			{
				"label": _("Sales"),
				"items": ["Solar Proposal", "Quotation"],
			},
			{
				"label": _("Execution"),
				"items": ["Solar Installation"],
			},
		],
	}
