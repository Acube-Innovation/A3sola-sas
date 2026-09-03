# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Platform Subscription, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "platform_subscription",
		"non_standard_fieldnames": {
			"Payment Order": "reference_name",
		},
		"dynamic_links": {
			"reference_name": ["Platform Subscription", "reference_doctype"],
		},
		"transactions": [
			{
				"label": _("Billing"),
				"items": ["Payment Order", "Payment Mandate", "Subscription Invoice"],
			},
			{
				"label": _("Provisioning"),
				"items": ["Provisioning Job", "Tenant"],
			},
		],
	}
