# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Tenant, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "tenant",
		"transactions": [
			{
				"label": _("Provisioning"),
				"items": ["Provisioning Job"],
			},
			{
				"label": _("Users"),
				"items": ["Tenant Invitation"],
			},
		],
	}
