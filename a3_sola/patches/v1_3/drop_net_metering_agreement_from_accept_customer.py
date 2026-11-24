# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Accept Customer task (ACPT) no longer asks for a Net Metering Agreement.

Its checklist is rebuilt from setup/seed_stages on migrate; each job's own register keeps the
row it was given, so it is taken off here - unless a signed copy was attached to it, which
stays on file, no longer required.
"""

import frappe

STAGE = "ACPT"
DOCUMENT = "Net Metering Agreement"


def execute():
	rows = frappe.get_all("Installation Document", filters={"parenttype": "Solar Installation", "stage_code": STAGE,
		"document_name": DOCUMENT}, fields=["name", "attachment", "is_verified"])
	for row in rows:
		if row.attachment or row.is_verified:
			frappe.db.set_value("Installation Document", row.name, "is_mandatory", 0, update_modified=False)
		else:
			frappe.db.delete("Installation Document", {"name": row.name})
	frappe.db.commit()
