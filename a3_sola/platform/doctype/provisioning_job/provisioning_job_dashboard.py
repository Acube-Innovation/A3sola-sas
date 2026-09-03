# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

# Connections panel: every downstream document of a Provisioning Job, so the
# chain can be walked forward from the form and the next document
# created with the + button.


from frappe import _


def get_data():
	return {
		"fieldname": "provisioning_job",
		"transactions": [
			{
				"label": _("Tenant"),
				"items": ["Tenant"],
			},
		],
	}
