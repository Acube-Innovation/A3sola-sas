# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Subscription Signup, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "subscription_signup",
		"transactions": [
			{
				"label": _("Payment"),
				"items": ["Payment Order", "Payment Mandate", "Subscription Invoice"],
			},
			{
				"label": _("Subscription"),
				"items": ["Platform Subscription"],
			},
			{
				"label": _("Provisioning"),
				"items": ["Provisioning Job", "Tenant"],
			},
		],
	}
