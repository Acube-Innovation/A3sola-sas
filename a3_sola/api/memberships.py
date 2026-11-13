# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One login, several companies, a different role in each.

Ali is a Dealer at one company and the Admin of another. He signs in once, picks the
company he is working in from the top bar, and everything follows that choice: his
roles, his menu, the records he sees, the company new records are made in.

HOW IT WORKS, AND WHY THIS WAY

Frappe keeps a user's roles and User Permissions per *user*, cached per user, and every
permission check in Frappe and in this app reads them that way: list views, reports,
link search, print, `api/permissions`, `api/partner_scope`, the isolation runner. Making
those per *session* would mean patching Frappe internals in four places.

So nothing is patched. Each company the person works in is a **Company Membership** row
holding their role there. Switching company *applies* that row to the real User:

* the roles become the membership's roles (plus any protected role the user holds);
* the single Company User Permission becomes the new company;
* the default company and the tenant stamp follow;
* Frappe recalculates whether they may use the desk.

Every existing guard then works exactly as it did, unchanged. The cost is the one stated
in the plan: the active company is per account, not per browser tab, so a switch in one
window applies to every window (the shell says so when it happens).

WHAT A SWITCH NEVER TOUCHES

The protected roles - the platform's own roles, System Manager, Administrator. A person
holding one of them is never shared between companies in the first place (see
`assert_shareable`), and if one is somehow held it survives every switch.

USERS WITH NO MEMBERSHIPS behave exactly as before. Every hook here returns early for
them, so nothing changes for anyone until they are given a second company.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from a3_sola.api.entitlements import TENANT_FIELD

DOCTYPE = "Company Membership"
ACTIVE_FIELD = "a3_sola_active_company"
#: Roles every user holds; never stored on a membership.
AUTOMATIC_ROLES = {"All", "Guest", "Desk User"}
#: Roles that belong to the instance or to the platform, never to one company.
PROTECTED = {"System Manager", "Administrator"}
TYPES = ("Admin", "Employee", "Contractor", "Dealer")
SKIP_FLAG = "a3s_applying_membership"


# ------------------------------------------------------------------ roles
def is_protected_role(role):
	return role in PROTECTED or (role or "").startswith("Platform ")


def protected_roles_of(user):
	return {r for r in frappe.get_roles(user) if is_protected_role(r)}


def is_protected_user(user):
	"""Platform staff, or an instance System Manager. Never shared between companies."""
	if user in ("Administrator", "Guest"):
		return True
	return bool(protected_roles_of(user))


def clean_roles(roles):
	"""A membership's roles: no automatic and no protected ones, no duplicates, real roles only."""
	out = []
	for role in roles or ():
		role = (role or "").strip()
		if role and role not in out and role not in AUTOMATIC_ROLES and not is_protected_role(role) \
				and frappe.db.exists("Role", role):
			out.append(role)
	return out


def profile_roles(profile):
	if not profile or not frappe.db.exists("Role Profile", profile):
		return []
	return [row.role for row in frappe.get_cached_doc("Role Profile", profile).roles]


def membership_roles(m):
	"""The roles a membership gives, less anything the company's plan does not include."""
	roles = [r.get("role") for r in (m.get("roles") or [])]
	if not roles:
		roles = profile_roles(m.get("role_profile"))
	roles = clean_roles(roles)
	if m.get("tenant"):
		from a3_sola.api.entitlements import forbidden_roles

		forbidden = forbidden_roles(m.get("tenant"))
		roles = [r for r in roles if r not in forbidden]
	return roles


def desk_access(roles):
	"""Whether these roles let their holder into the desk - Frappe's own rule (user_type)."""
	roles = [r for r in roles or () if r not in AUTOMATIC_ROLES]
	if not roles:
		return False
	return bool(frappe.get_all("Role", filters={"name": ["in", roles], "desk_access": 1}, limit=1))


# ------------------------------------------------------------------ reading
def has_memberships(user=None):
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return False
	return bool(frappe.db.exists(DOCTYPE, {"user": user}))


def active_company(user=None):
	"""The company this user is working in, when they have memberships; else None."""
	user = user or frappe.session.user
	if user in ("Administrator", "Guest") or not frappe.get_meta("User").has_field(ACTIVE_FIELD):
		return None
	return frappe.get_cached_value("User", user, ACTIVE_FIELD) or None


def get_membership(user, company):
	name = frappe.db.get_value(DOCTYPE, {"user": user, "company": company}, "name")
	return frappe.get_doc(DOCTYPE, name) if name else None


def active_membership(user=None):
	user = user or frappe.session.user
	company = active_company(user)
	return get_membership(user, company) if company else None


def memberships(user=None, enabled_only=True):
	"""The user's companies, newest-worked-in first, with what the switcher shows."""
	user = user or frappe.session.user
	filters = {"user": user}
	if enabled_only:
		filters["enabled"] = 1
	rows = frappe.get_all(DOCTYPE, filters=filters, fields=["name", "company", "tenant", "portal_type", "is_admin",
		"enabled", "suspended_by", "last_active_on"], order_by="last_active_on desc, creation asc")
	active = active_company(user)
	for row in rows:
		name, logo = frappe.db.get_value("Company", row.company, ["company_name", "company_logo"]) or (None, None)
		row.company_name = name or row.company
		row.logo = logo or None
		row.is_active = row.company == active
		row.eligible = eligible(row)
		row.paused = bool(row.enabled) and not row.eligible
	return rows


def eligible(m):
	"""May this membership be worked in right now?"""
	if not cint(m.get("enabled")) or m.get("suspended_by"):
		return False
	tenant = m.get("tenant")
	if tenant:
		status, gate = frappe.db.get_value("Tenant", tenant, ["status", "access_gate"]) or (None, None)
		if status in ("Cancelled", "Terminated") or gate == "Blocked":
			return False
	return True


def pick_default(user, exclude=None):
	"""The company to open: the active one while it may be worked in, else the latest one that can."""
	rows = [r for r in memberships(user) if r.company != exclude]
	for row in rows:
		if row.is_active and row.eligible:
			return row.company
	return next((r.company for r in rows if r.eligible), None)


def is_shared(user):
	"""Whether this login works in more than one company (enabled or not)."""
	return frappe.db.count(DOCTYPE, {"user": user}) > 1


def company_permissions(user):
	return frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")


# ------------------------------------------------------------------ writing
def assert_shareable(user):
	"""Refuse to give a second company to someone whose roles span the instance."""
	if is_protected_user(user):
		frappe.throw(_("{0} holds an instance-wide role (System Manager or a platform role), so the account "
			"cannot be added to another company. Use a different e-mail address for this company.").format(user),
			title=_("Account Cannot Be Shared"))


def ensure_membership(user, company, portal_type, *, roles=None, role_profile=None, also_kind=0,
		designation=None, department=None, enabled=1, source="Manual", apply=False):
	"""Create or update the user's membership in a company. Returns the document."""
	if portal_type not in TYPES:
		frappe.throw(_("Choose the kind of user: Admin, Employee, Contractor or Dealer."))
	doc = get_membership(user, company)
	if not doc:
		doc = frappe.new_doc(DOCTYPE)
		doc.user, doc.company, doc.source = user, company, source
		doc.added_by = frappe.session.user
	doc.portal_type = portal_type
	doc.role_profile = role_profile or None
	doc.also_kind = cint(also_kind)
	doc.enabled = cint(enabled)
	if designation is not None:
		doc.designation = designation or None
	if department is not None:
		doc.department = department or None
	if roles is not None:
		doc.set("roles", [{"role": r} for r in clean_roles(roles)])
	doc.flags.ignore_permissions = True
	doc.flags.a3s_apply = apply
	doc.save(ignore_permissions=True)
	return doc


def record_current(user, company, portal_type=None, source="Manual"):
	"""Write down a single-company login's access as its membership there, exactly as it is now.

	Nothing about the user changes. Used when a login is made (portal, provisioning,
	invitation) and by the migration, so that the day they are given a second company
	their first one is already on record.
	"""
	if not company or is_shared(user):
		return None
	from a3_sola.api.portal_users import both_kinds, type_of

	row = frappe.db.get_value("User", user, ["name", "role_profile_name", "enabled"], as_dict=True)
	if not row:
		return None
	held = frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role", order_by="idx asc")
	doc = ensure_membership(user, company, portal_type or type_of(row), roles=held, role_profile=row.role_profile_name,
		also_kind=cint(both_kinds(user)), enabled=cint(row.enabled), source=source)
	if not active_company(user):
		frappe.db.set_value("User", user, ACTIVE_FIELD, company, update_modified=False)
		frappe.clear_cache(user=user)
	return doc


def apply_membership(user, company, *, force=False):
	"""Make the user's real Frappe state that of their membership in `company`.

	The one function that writes it. Locks the User row first, so two windows switching
	at once are applied one after the other rather than interleaved.
	"""
	from a3_sola.api.lifecycle import gate
	from a3_sola.api.tenant_users import _set_default_company, ensure_company_permission

	frappe.db.sql("select name from `tabUser` where name = %s for update", user)
	m = get_membership(user, company)
	if not m:
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	if not force and not eligible(m):
		frappe.throw(_("{0} is not available to work in right now.").format(company), title=_("Company Paused"))

	doc = frappe.get_doc("User", user)
	keep = [r.role for r in doc.roles if is_protected_role(r.role)]
	roles = membership_roles(m)
	profile = m.role_profile if m.role_profile and not keep and set(profile_roles(m.role_profile)) == set(roles) else None
	doc.role_profile_name = profile
	doc.set("roles", [])
	doc.append_roles(*dict.fromkeys(keep + roles))
	doc.set(ACTIVE_FIELD, company)
	if frappe.get_meta("User").has_field(TENANT_FIELD):
		doc.set(TENANT_FIELD, m.tenant or None)
	doc.flags.ignore_permissions = True
	doc.flags.a3s_skip_quota = True
	doc.flags[SKIP_FLAG] = True
	doc.save(ignore_permissions=True)

	# The new company first, then the others go: there is never a moment with none, which
	# Frappe would read as "unrestricted". Frappe allows one default per user, so the old
	# ones stop being the default before the new one is added as it.
	others = frappe.get_all("User Permission", filters={"user": user, "allow": "Company",
		"for_value": ["!=", company]}, pluck="name")
	for name in others:
		frappe.db.set_value("User Permission", name, "is_default", 0, update_modified=False)
	ensure_company_permission(user, company)
	for name in others:
		frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)
	if company_permissions(user) != [company]:
		frappe.throw(_("The company permission for {0} could not be verified, so the switch was stopped.").format(user),
			title=_("Isolation Not Established"))
	_set_default_company(user, company)
	frappe.db.set_value(DOCTYPE, m.name, "last_active_on", now_datetime(), update_modified=False)

	frappe.clear_cache(user=user)
	frappe.cache.hdel("user_permissions", user)
	gate.invalidate(user=user)
	if user == frappe.session.user:
		_stamp_session(company, frappe.db.get_value("User", user, "user_type"))
	return m


def _stamp_session(company, user_type=None):
	session_obj = getattr(frappe.local, "session_obj", None)
	if not session_obj or frappe.session.user in ("Guest", None):
		return
	data = session_obj.data.data
	data["a3s_company"] = company
	if user_type:
		data["user_type"] = user_type
	session_obj.update(force=True)


def leave_if_active(user, company):
	"""The membership in `company` can no longer be worked in: move the user off it.

	To their next company when there is one. When there is none, the login is disabled
	rather than its company permission removed - no company permission at all reads as
	"sees every company".
	"""
	if active_company(user) != company:
		return None
	other = pick_default(user, exclude=company)
	if other:
		apply_membership(user, other)
	else:
		# Nothing open to them. A paused company still beats none: they are moved there and
		# the gate refuses them until it reopens. Only with no other company at all is the
		# login disabled.
		paused = next((r.company for r in memberships(user) if r.company != company), None)
		if paused:
			apply_membership(user, paused, force=True)
		else:
			frappe.db.set_value("User", user, "enabled", 0)
			frappe.clear_cache(user=user)
	frappe.sessions.clear_sessions(user=user, force=True)
	return other


def remove_membership(user, company):
	"""Take a company away from a shared login. The user stays for their other companies."""
	m = get_membership(user, company)
	if not m:
		return
	m.flags.ignore_permissions = True
	m.delete(ignore_permissions=True)


# ------------------------------------------------------------------ endpoints
@frappe.whitelist(methods=["POST"])
def switch_company(company):
	"""The top bar's company switcher."""
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from a3_sola.api import impersonation

	if impersonation.current():
		frappe.throw(_("A support session is locked to one company. Return to your own account first."),
			frappe.PermissionError, title=_("Not While Viewing As"))
	if impersonation.active_for_target(user):
		frappe.throw(_("Someone from support is working in your account right now, so the company cannot be "
			"changed until they finish."), title=_("Support Session Open"))
	m = get_membership(user, company)
	if not m or not cint(m.enabled):
		frappe.throw(_("Not found"), frappe.DoesNotExistError)
	if not eligible(m):
		frappe.throw(_("{0} is paused, so it cannot be opened right now.").format(
			frappe.db.get_value("Company", company, "company_name") or company), title=_("Company Paused"))
	apply_membership(user, company)
	frappe.get_doc({"doctype": "Activity Log", "user": user, "status": "Success", "operation": "Login",
		"subject": _("Switched to company {0}").format(company), "full_name": frappe.utils.get_fullname(user)}
		).insert(ignore_permissions=True)
	return {"company": company, "redirect": "/a3solaportal/dashboard"}


@frappe.whitelist()
def my_companies():
	"""The signed-in user's own companies - never anyone else's."""
	if frappe.session.user in ("Guest", "Administrator"):
		return []
	return [{k: r.get(k) for k in ("company", "company_name", "logo", "portal_type", "is_admin", "is_active",
		"paused")} for r in memberships(frappe.session.user)]


# ------------------------------------------------------------------ hooks
def on_session_creation(login_manager=None):
	"""At sign-in: open the last company worked in, or the next one if it is paused."""
	user = frappe.session.user
	if frappe.flags.a3s_impersonating or user in ("Guest", "Administrator") or not has_memberships(user):
		return
	target = pick_default(user)
	if not target:
		return  # nothing open to them: the gate refuses the sign-in, as it does today
	if target != active_company(user) or company_permissions(user) != [target]:
		apply_membership(user, target)
	else:
		_stamp_session(target)


def sync_session():
	"""`before_request`: notice a switch made in another window or device."""
	user = frappe.session.user
	if user in ("Guest", "Administrator", None):
		return
	data = frappe.session.data
	if data.get("impersonated_by"):
		return
	company = active_company(user)
	if not company or data.get("a3s_company") == company:
		return
	previous = data.get("a3s_company")
	_stamp_session(company, frappe.get_cached_value("User", user, "user_type"))
	if previous:
		frappe.local.a3s_company_changed = company


def reconcile_user_roles(doc, method=None):
	"""User `validate`: keep a shared login's roles those of the company it is working in.

	Roles reach a User other ways than a switch - ERPNext gives Employee back whenever an
	Employee record is saved, someone ticks a role in the desk. For a login in one company
	that is fine and the membership follows (`sync_membership`). For a shared login it is
	how a Dealer at one company would keep an Admin's roles from another, so any role the
	active membership does not give is taken off again.
	"""
	if doc.flags.get(SKIP_FLAG) or frappe.flags.in_install or frappe.flags.in_migrate or doc.is_new():
		return
	company = doc.get(ACTIVE_FIELD)
	if not company or frappe.db.count(DOCTYPE, {"user": doc.name}) < 2:
		return
	m = get_membership(doc.name, company)
	if not m:
		return
	allowed = set(membership_roles(m))
	stray = [r.role for r in doc.roles if r.role not in allowed and not is_protected_role(r.role)
		and r.role not in AUTOMATIC_ROLES]
	if not stray:
		return
	doc.set("roles", [r for r in doc.roles if r.role not in stray])
	if doc.role_profile_name and set(profile_roles(doc.role_profile_name)) != allowed:
		doc.role_profile_name = None
	frappe.msgprint(_("{0} works in more than one company, so their roles are set per company on the portal's Users "
		"page. These were not kept: {1}").format(doc.name, ", ".join(stray)), indicator="orange", alert=True)


def sync_membership(doc, method=None):
	"""User `on_update`: a login in one company keeps its membership in step with its roles.

	Written to the membership's rows directly, not by saving it, so it cannot come back
	round to the User.
	"""
	if doc.flags.get(SKIP_FLAG) or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	if doc.name in ("Administrator", "Guest") or frappe.db.count(DOCTYPE, {"user": doc.name}) != 1:
		return
	m = frappe.get_doc(DOCTYPE, frappe.db.get_value(DOCTYPE, {"user": doc.name}, "name"))
	roles = clean_roles([r.role for r in doc.roles])
	if roles == [r.role for r in m.roles] and (doc.role_profile_name or None) == (m.role_profile or None):
		return
	from a3_sola.api.portal_users import type_of

	frappe.db.delete("Company Membership Role", {"parent": m.name, "parenttype": DOCTYPE})
	for i, role in enumerate(roles, 1):
		frappe.get_doc({"doctype": "Company Membership Role", "parent": m.name, "parenttype": DOCTYPE,
			"parentfield": "roles", "idx": i, "role": role}).db_insert()
	values = {"role_profile": doc.role_profile_name or None, "desk_access": cint(desk_access(roles)),
		"portal_type": type_of(frappe._dict(name=doc.name, role_profile_name=doc.role_profile_name,
			enabled=doc.enabled))}
	values["counts_seat"] = values["desk_access"]
	values["is_admin"] = cint(values["portal_type"] == "Admin")
	frappe.db.set_value(DOCTYPE, m.name, values, update_modified=False)
