# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every user becomes exactly one kind - Admin, Employee, Dealer or Contractor - with that
kind's one role profile.

- An Admin stays as he is: his profile, or the System Manager's own roles.
- An Employee gets the Solar Employee profile: every staff job's access. Roles ticked one by
  one, and roles given in the desk, go.
- A Dealer or Contractor gets his own profile only: a dealer who was also a contractor stays
  a Dealer (and is no longer his contractor record's login), and the staff jobs a partner was
  given go.

A login in several companies is changed in each company's membership, and the company it is
working in now is applied to the login. Customers of the customer portal, Acube's platform
staff, Administrator and Guest are left alone.
"""

import frappe
from frappe.utils import cint

from a3_sola.api import memberships
from a3_sola.api import portal_users as pu
from a3_sola.setup import employee_profile


def execute():
	if not employee_profile.ensure():
		return  # the staff profiles are not on this site
	internal = pu._internal_users()
	users = frappe.get_all("User", filters={"name": ["not in", list(pu.HIDDEN_USERS)],
		"user_type": ["in", ["System User", "Website User"]]}, fields=["name", "role_profile_name", "enabled", "user_type"])
	for row in users:
		if row.name in internal:
			continue
		try:
			if frappe.db.exists(memberships.DOCTYPE, {"user": row.name}):
				_convert_memberships(row)
			else:
				_convert_login(row)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"a3_sola: one user type - {row.name}")
		else:
			frappe.db.commit()


def _kind(row):
	"""His kind as the Users page reads it, a disabled login's too."""
	return pu.type_of(frappe._dict(row, enabled=1))


def _is_customer(row, kind):
	return row.user_type == "Website User" and kind == "Employee"


def _convert_login(row):
	kind = _kind(row)
	if kind == "Admin" or _is_customer(row, kind):
		return
	profile = pu.PROFILE_OF[kind]
	if row.role_profile_name == profile and set(pu._roles(row.name)) == set(memberships.profile_roles(profile)):
		return
	user = frappe.get_doc("User", row.name)
	user.role_profile_name = profile
	user.flags.ignore_permissions = True
	user.flags.a3s_skip_quota = True
	user.save(ignore_permissions=True)
	if kind == "Dealer":
		frappe.db.sql("update `tabSolar Contractor` set user = null where user = %s", row.name)


def _convert_memberships(row):
	for name in frappe.get_all(memberships.DOCTYPE, filters={"user": row.name}, pluck="name"):
		m = frappe.get_doc(memberships.DOCTYPE, name)
		if m.portal_type == "Admin" or m.portal_type not in pu.PROFILE_OF:
			continue
		profile = pu.PROFILE_OF[m.portal_type]
		roles = memberships.clean_roles(memberships.profile_roles(profile))
		if m.role_profile == profile and not cint(m.also_kind) and [r.role for r in m.roles] == roles:
			continue
		m.role_profile, m.also_kind = profile, 0
		m.set("roles", [{"role": r} for r in roles])
		m.flags.ignore_permissions = True
		frappe.flags.a3s_migrating = True  # no seat check, and the login is applied below
		try:
			m.save(ignore_permissions=True)
		finally:
			frappe.flags.a3s_migrating = False
		if m.portal_type == "Dealer":
			frappe.db.sql("update `tabSolar Contractor` set user = null where user = %s and ifnull(company, '') in (%s, '')",
				(row.name, m.company))
	active = memberships.active_company(row.name)
	if active and memberships.get_membership(row.name, active):
		m = memberships.get_membership(row.name, active)
		if m.portal_type != "Admin":
			memberships.apply_membership(row.name, active, force=True)
	elif not memberships.is_shared(row.name):
		_convert_login(row)
