# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Component Make's free-text technology becomes a link to the Component Technology master.

Each distinct technology a company has typed on its makes, per component type, becomes one
master record of that company, and the makes are pointed at it. Estimate options kept the
technology as text and stay as they are.
"""

import frappe


def execute():
	makes = frappe.db.sql(
		"""select name, technology, component_type, company from `tabComponent Make`
		where ifnull(technology, '') != ''
		and technology not in (select name from `tabComponent Technology`)""",
		as_dict=True,
	)
	created = {}
	for make in makes:
		key = (make.technology, make.component_type, make.company)
		if key not in created:
			existing = frappe.db.get_value(
				"Component Technology",
				{"technology_name": make.technology, "component_type": make.component_type, "company": make.company},
			)
			if not existing:
				doc = frappe.get_doc(
					{
						"doctype": "Component Technology",
						"technology_name": make.technology,
						"component_type": make.component_type,
						"company": make.company,
						"is_active": 1,
					}
				)
				doc.flags.ignore_mandatory = True
				doc.insert(ignore_permissions=True)
				existing = doc.name
			created[key] = existing
		frappe.db.set_value("Component Make", make.name, "technology", created[key], update_modified=False)
	frappe.db.commit()
	print(f"a3_sola: {len(makes)} component make(s) linked to {len(created)} technolog(ies)")
