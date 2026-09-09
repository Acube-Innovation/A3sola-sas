# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Billing milestones keyed to old chain codes now key to tasks.

INST (the installation stage) is the installation work order, IWOI; KTST (the DISCOM test)
was where the completion documents used to land, and that is the KSEB submission pack,
KFORMS. Template rows and untriggered plan rows are repointed; a triggered row is history
and keeps the code it fired on.
"""

import frappe


def execute():
	from a3_sola.api.billing import TRIGGER_CODE_MAP

	changed = 0
	for doctype, extra in (
		("Billing Milestone Template Detail", {}),
		("Billing Milestone Entry", {"is_triggered": 0}),
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		for old, new in TRIGGER_CODE_MAP.items():
			for name in frappe.get_all(doctype, filters={"trigger_stage_code": old, **extra}, pluck="name"):
				frappe.db.set_value(doctype, name, "trigger_stage_code", new, update_modified=False)
				changed += 1
	frappe.db.commit()
	print(f"a3_sola: {changed} billing milestone row(s) repointed to task codes")
	return changed
