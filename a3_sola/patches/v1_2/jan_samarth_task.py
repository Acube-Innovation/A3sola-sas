# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Digital Approval Letter task is "Jan Samarth", done on the PM Surya Ghar side: on the
shared template and every project it moves to the PM Surya Ghar column (Scheme Activity) -
shown only on a job that takes a loan - and its letter is the "Jan Samarth approval letter"."""

import frappe

from a3_sola.setup import install_ops

CODE = "DAL"
OLD_DOCUMENT, NEW_DOCUMENT = "Digital approval letter", "Jan Samarth approval letter"


def execute():
	install_ops.setup()  # the template row's name, and the task's checklist
	name = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	row = frappe.db.get_value("Installation Stage Template Detail", {"parent": name, "stage_code": CODE},
		["stage_name", "activity_scope"], as_dict=True) if name else None
	if not row:
		return
	scope = "Scheme Activity"
	frappe.db.set_value("Installation Stage Template Detail", {"parent": name, "stage_code": CODE},
		"activity_scope", scope, update_modified=False)
	# Every job's save copies the task's scope from the cached template (stages.sync_from_template):
	# a stale copy would put the task back in the Bank column.
	frappe.clear_document_cache("Installation Stage Template", name)
	frappe.db.sql("""update `tabInstallation Stage Log` set stage_name=%s, activity_scope=%s
		where stage_code=%s and parenttype='Solar Installation'""", (row.stage_name, scope, CODE))
	frappe.db.sql("""update `tabInstallation Document` set document_name=%s
		where stage_code=%s and document_name=%s and parenttype='Solar Installation'""", (NEW_DOCUMENT, CODE, OLD_DOCUMENT))
	frappe.db.sql("""update `tabDocument Checklist Template Item` set document_name=%s
		where document_name=%s""", (NEW_DOCUMENT, OLD_DOCUMENT))
