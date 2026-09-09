# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One Installation Stage Template, shared by every company.

The thirty tasks are the same for every solar company on the site, so a copy per company
was clutter - and, with the retired pre-task templates still around, two hundred and
seventy-eight documents where one is meant. This creates the shared template (no company),
points every installation at it (its task rows are its own and do not change), points
Settings at it, and deletes every other Installation Stage Template. A template something
still links is deactivated instead and named in the error log.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Installation Stage Template"):
		return None
	frappe.reload_doc("solar_operations", "doctype", "installation_stage_template")
	from a3_sola.setup import install_ops

	# An earlier run may have inserted the shared template only for Frappe to stamp the
	# default company on it; whichever template Settings names, or the oldest task template,
	# becomes the shared one rather than yet another copy.
	if not frappe.db.exists("Installation Stage Template", {"is_shared": 1}):
		candidate = frappe.db.get_single_value("A3 Sola Settings", "default_stage_template")
		if not (candidate and frappe.db.exists("Installation Stage Template", candidate)):
			candidate = frappe.db.get_value(
				"Installation Stage Template", {"template_name": install_ops.TASK_TEMPLATE_NAME}, "name",
				order_by="creation asc",
			)
		if candidate:
			frappe.db.set_value(
				"Installation Stage Template", candidate,
				{"is_shared": 1, "company": None, "is_active": 1, "is_default": 1}, update_modified=False,
			)
	shared = install_ops.seed_stage_templates()
	repointed = 0
	for name in frappe.get_all(
		"Solar Installation", filters={"stage_template": ["!=", shared]}, pluck="name"
	):
		frappe.db.set_value("Solar Installation", name, "stage_template", shared, update_modified=False)
		repointed += 1
	settings = frappe.get_single("A3 Sola Settings")
	if settings.default_stage_template != shared:
		settings.default_stage_template = shared
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)

	deleted = kept = 0
	for name in frappe.get_all("Installation Stage Template", filters={"name": ["!=", shared]}, pluck="name"):
		frappe.db.savepoint("a3s_template")
		try:
			frappe.delete_doc("Installation Stage Template", name, force=True, ignore_permissions=True)
			deleted += 1
		except Exception:
			frappe.db.rollback(save_point="a3s_template")
			frappe.db.set_value(
				"Installation Stage Template", name, {"is_active": 0, "is_default": 0}, update_modified=False
			)
			kept += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: stage template {name} still linked, deactivated")
	frappe.db.commit()
	print(
		f"a3_sola: one shared task template {shared}; {repointed} installation(s) repointed, "
		f"{deleted} template(s) deleted, {kept} kept inactive"
	)
	return {"shared": shared, "repointed": repointed, "deleted": deleted, "kept": kept}
