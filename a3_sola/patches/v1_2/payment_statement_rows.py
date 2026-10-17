# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Each payment task (ADV, BAL, PCOM) lists the Payment Statement: the template and the tasks'
checklists take it (install_ops re-syncs them from seed_documents and seed_stages), and every
running job with the task gets the row - printed live, so it needs no file.
"""

import frappe

from a3_sola.setup import install_ops

CODE = "PAYMENT-STATEMENT"
NAME = "Payment statement"
TASKS = ("ADV", "BAL", "PCOM")


def execute():
	install_ops.setup()
	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		inst = frappe.get_doc("Solar Installation", name)
		template = frappe.db.get_value("Solar Document Template", {"template_code": CODE, "company": inst.company}, "name") \
			or frappe.db.get_value("Solar Document Template", {"template_code": CODE}, "name")
		codes = {r.stage_code for r in inst.stages if r.status != "Skipped"}
		have = {d.stage_code for d in inst.documents if d.document_name == NAME}
		added = False
		for code in TASKS:
			if code in codes and code not in have:
				inst.append("documents", {"stage_code": code, "document_name": NAME, "document_kind": "Expected",
					"is_mandatory": 0, "solar_document_template": template})
				added = True
		if added:
			inst.flags.ignore_validate_update_after_submit = True
			inst.flags.ignore_permissions = True
			inst.flags.ignore_links = True
			inst.save(ignore_permissions=True)
