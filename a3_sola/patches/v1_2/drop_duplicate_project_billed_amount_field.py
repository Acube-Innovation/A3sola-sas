# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Project stops carrying two fields called total_billed_amount.

ERPNext already ships total_billed_amount on Project. This module declared it a second
time as a Custom Field to put it at permlevel 1, and create_custom_fields(
ignore_validate=True) let that through - so the doctype ended up with two DocFields of
one name. Nothing complained until another app inserted any Custom Field on Project: that
runs validate_fields() over the whole doctype, which raised UniqueFieldnameError and left
the other app unable to install.

The duplicate is removed and the permlevel guarantee moves onto ERPNext's own field, so a
service technician still cannot read what a project has billed. The column belongs to the
standard field and is left alone; no amount is touched.

Order matters here. Custom Field.on_trash deletes every Property Setter for its doc_type
and field_name, so the re-grade has to come AFTER the delete - applying it first would
leave the field at permlevel 0 with nothing to show for the patch.
"""

import frappe


def execute():
	from a3_sola.setup.install import install_property_setters

	name = "Project-total_billed_amount"
	if frappe.db.exists("Custom Field", name):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
		print(f"a3_sola: removed duplicate Custom Field {name}")
	else:
		print(f"a3_sola: no duplicate {name} to remove")

	# After the delete, never before: see the note above.
	install_property_setters()

	frappe.clear_cache(doctype="Project")
	frappe.db.commit()
