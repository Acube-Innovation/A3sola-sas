# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Form 3 Submission no longer lists "AE acknowledged Form 3": the task's checklist drops
it (install_ops re-syncs it from seed_stages), and so do the running jobs - but only the rows
still waiting for a file. A row with an acknowledgement already uploaded keeps it.
"""

import frappe

from a3_sola.setup import install_ops

NAME = "AE acknowledged Form 3"


def execute():
	install_ops.setup()
	for row in frappe.get_all("Installation Document", filters={"parenttype": "Solar Installation",
			"stage_code": "KFORMS", "document_name": NAME}, fields=["name", "attachment"]):
		if not row.attachment:
			frappe.db.delete("Installation Document", {"name": row.name})
