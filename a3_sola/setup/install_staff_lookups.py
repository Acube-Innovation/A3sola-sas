# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Read access for every staff role to the lookup lists the sales forms pick from. Idempotent;
run on every migrate.

A Link field's dropdown on the portal lists only what the user may read (api/portal_fields
.link_choices), so a role without read on Indian District saw an empty District list - a Sales
Coordinator, say, who held no other role. These are reference lists - places, the electricity
board's sections and tariffs, the lead's source and segment - not business records, so every
staff role reads them. Nothing here grants write, and no record a role could not already reach.

The grant is a Custom DocPerm, after `setup_custom_perms` copies the doctype's standard rows:
the moment a doctype has any Custom DocPerm, Frappe stops reading its standard ones
(install_partners explains).
"""

import frappe

#: The lookup lists of the Lead, Customer, Site Survey, Design Estimate, Eligibility and
#: Proposal forms. Read and select only.
LOOKUPS = (
	"Indian State", "Indian District", "DISCOM", "DISCOM Section", "KSEB Tariff Category",
	"Electricity Tariff", "Roof Type", "Subsidy Scheme", "Lead Source", "Territory", "Campaign",
	"Industry Type", "Market Segment",
)


def staff_roles():
	"""Every role a staff profile gives, Employee included."""
	from a3_sola.api.portal_users import BASE_ROLE
	from a3_sola.api.portal_users import staff_roles as tickable

	return [r for r in [BASE_ROLE, *tickable()] if frappe.db.exists("Role", r)]


def setup():
	from frappe.permissions import setup_custom_perms

	roles = staff_roles()
	for doctype in LOOKUPS:
		if not frappe.db.exists("DocType", doctype):
			continue
		setup_custom_perms(doctype)
		for role in roles:
			name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0})
			if name:
				frappe.db.set_value("Custom DocPerm", name, {"read": 1, "select": 1}, update_modified=False)
			else:
				frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType",
					"parentfield": "permissions", "role": role, "permlevel": 0, "read": 1, "select": 1}
				).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
