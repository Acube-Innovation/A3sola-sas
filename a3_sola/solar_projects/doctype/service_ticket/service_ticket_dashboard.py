# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Service Ticket, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "service_ticket",
		"non_standard_fieldnames": {
			"Generation Reading": "triggered_ticket",
		},
		"transactions": [
			{
				"label": _("Resolution"),
				"items": ["Solar OM Visit", "Solar Warranty Claim"],
			},
			{
				"label": _("Monitoring"),
				"items": ["Generation Reading"],
			},
		],
	}
