# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One task template per company, in place of the residential/commercial pair.

Every company used to get two stage templates and a scorer picked between them. Tasks are
independent now and a commercial job simply pre-skips the subsidy tasks, so there is one
template - "Solar Installation Tasks" - and nothing to pick.

This seeds that template for every company (with the document templates and expected-
document lists it links, in that order), then retires the two old ones by deactivating
them. They are not deleted: every open installation still links its old template until
`rebuild_installation_tasks` re-points it, and a `reqd` Link to a deleted record refuses to
save. Settings' default template is repointed so no new job can be built on the old chain.

Patches run before `after_migrate` seeding, so the seeding here is not redundant: without
it a site would reach the rebuild patch with no template to rebuild onto.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Installation Stage Template"):
		return None
	from a3_sola.setup import install_ops

	seeded, retired = 0, 0
	for company in frappe.get_all("Company", pluck="name"):
		frappe.db.savepoint("a3s_task_template")
		try:
			install_ops.seed_document_templates(company)
			install_ops.seed_checklists(company)
			install_ops.seed_stage_templates(company)
			install_ops.backfill_checklist_links(company)
			retired += install_ops.deactivate_legacy_templates(company)
			install_ops._set_defaults(company)
			seeded += 1
		except Exception:
			frappe.db.rollback(save_point="a3s_task_template")
			frappe.log_error(frappe.get_traceback(), f"a3_sola: task template seeding failed for {company}")
	frappe.db.commit()
	print(f"a3_sola: task template seeded for {seeded} company(ies); {retired} legacy template(s) retired")
	return {"seeded": seeded, "retired": retired}
