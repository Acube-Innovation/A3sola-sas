# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The net-metering agreement the Form 3 Submission asks for is the "KSEB Solar Agreement":
the template, the task's checklist (install_ops re-syncs it from seed_stages) and the
Expected rows already on running jobs take the name.
"""

import frappe

from a3_sola.setup import install_ops

CODE = "KSEB-NETMETER-AGREEMENT"
OLD_NAMES = ("Net metering agreement", "Net Metering Agreement (Stamp Paper)")
NAME = "KSEB Solar Agreement"


def execute():
	install_ops.setup()
	templates = frappe.get_all("Solar Document Template", filters={"template_code": CODE}, pluck="name")
	for name in templates:
		frappe.db.set_value("Solar Document Template", name, "document_name", NAME, update_modified=False)
	rows = frappe.get_all("Installation Document", filters={"parenttype": "Solar Installation", "stage_code": "KFORMS",
		"document_name": ["in", OLD_NAMES]}, pluck="name")
	if templates:
		rows += frappe.get_all("Installation Document", filters={"parenttype": "Solar Installation",
			"solar_document_template": ["in", templates], "document_name": ["!=", NAME]}, pluck="name")
	for row in set(rows):
		frappe.db.set_value("Installation Document", row, "document_name", NAME, update_modified=False)
