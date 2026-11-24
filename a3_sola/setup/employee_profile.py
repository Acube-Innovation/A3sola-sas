# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The one access every Employee holds: the Solar Employee role profile.

An Employee works a customer the whole way - the lead, the survey and design, the proposal,
the project and its tasks, accounts and service - so the profile is every staff job's roles
together. Only the company's setup (Solar CRM Manager, which makes its holder an admin) is
left to Admin.

It is built from the staff profiles (api/portal_users.STAFF_PROFILES) each migrate, so a role
added to any of them reaches every Employee too: Frappe gives a profile's users its roles
whenever the profile is saved.
"""

import frappe

EMPLOYEE_PROFILE = "Solar Employee"
#: Kept for Admin: these make their holder an administrator.
ADMIN_ONLY_ROLES = ("Solar CRM Manager", "System Manager")


def employee_roles():
	"""Employee, then every staff profile's roles in the order the work happens, less Admin's."""
	from a3_sola.api.portal_users import BASE_ROLE, staff_profile_roles

	out = [BASE_ROLE]
	for roles in staff_profile_roles().values():
		out.extend(r for r in roles if r not in out and r not in ADMIN_ONLY_ROLES)
	return [r for r in out if frappe.db.exists("Role", r)]


def ensure():
	"""Create the profile, or bring its roles in step with the staff profiles. Idempotent."""
	roles = employee_roles()
	if len(roles) < 2:
		return None  # the staff profiles are not set up yet (a fresh install, part way)
	if frappe.db.exists("Role Profile", EMPLOYEE_PROFILE):
		doc = frappe.get_doc("Role Profile", EMPLOYEE_PROFILE)
		if [r.role for r in doc.roles] == roles:
			return doc
		doc.set("roles", [{"role": r} for r in roles])
		doc.save(ignore_permissions=True)
		return doc
	return frappe.get_doc({"doctype": "Role Profile", "role_profile": EMPLOYEE_PROFILE,
		"roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)
