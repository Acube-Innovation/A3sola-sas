# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's Users page: an admin adds, edits, disables or deletes the people who use the
system, resets their passwords and sends them their welcome - all without the ERPNext desk.

Four kinds of user, each a role profile:

- **Admin** - Solar Tenant Administrator: runs the company's setup, and this page;
- **Employee** - one of the staff profiles (Solar Sales, Solar Operations, ...);
- **Contractor** - Solar Contractor: a partner who sees only the projects he is contractor on,
  through his Solar Contractor record's Portal User (api/partner_scope);
- **Dealer** - Solar Dealer: a partner who sees only the customers he brought in.

Only an admin may use any of it. Nobody is given a password by default: a new user is sent a
set-password link, by WhatsApp or e-mail, and chooses his own.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, get_url

from a3_sola.api import partner_scope
from a3_sola.api.permissions import get_permitted_companies

ADMIN_ROLES = ("System Manager", "Solar CRM Manager")
ADMIN_PROFILE = "Solar Tenant Administrator"
DEALER_PROFILE = "Solar Dealer"
CONTRACTOR_PROFILE = "Solar Contractor"
#: The staff profiles an Employee may be given, in the order the work happens.
STAFF_PROFILES = (
	"Solar Sales", "Solar Sales Coordination", "Solar Survey", "Solar Design", "Solar Sales Management",
	"Solar CRM Administration", "Solar Operations", "Solar Documentation", "Solar Field Crew",
	"Solar Operations Management", "Solar Projects Management", "Solar Service", "Solar Service Management",
)
#: Every staff member holds this; it is added for them and never ticked by hand.
BASE_ROLE = "Employee"
TYPES = ("Admin", "Employee", "Contractor", "Dealer")
PROFILE_OF = {"Admin": ADMIN_PROFILE, "Dealer": DEALER_PROFILE, "Contractor": CONTRACTOR_PROFILE}
CONTRACTOR_TYPES = ("Electrical", "Structural", "EPC", "Other")
HIDDEN_USERS = ("Administrator", "Guest")
LOGIN_PATH = "/a3solaportal/login"
SET_PASSWORD_PATH = "/a3solaportal/set-password"


# ------------------------------------------------------------------ who may
def is_user_admin(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if user == "Guest" or partner_scope.is_partner(user):
		return False
	if set(frappe.get_roles(user)) & set(ADMIN_ROLES):
		return True
	return frappe.db.get_value("User", user, "role_profile_name") == ADMIN_PROFILE


def require_admin():
	if not is_user_admin():
		frappe.throw(_("Only an administrator can do this."), frappe.PermissionError, title=_("Not Permitted"))


# ------------------------------------------------------------------ reading
def _internal_users():
	"""Users holding the platform's own roles - Acube's staff, never the tenant's to manage."""
	from a3_sola.api.entitlements import INTERNAL_PLATFORM_ROLES

	return set(frappe.get_all("Has Role", filters={"parenttype": "User", "role": ["in", list(INTERNAL_PLATFORM_ROLES)]},
		pluck="parent"))


def _tenant_field():
	from a3_sola.api.entitlements import TENANT_FIELD

	return TENANT_FIELD if frappe.get_meta("User").has_field(TENANT_FIELD) else None


def type_of(user):
	"""Admin, Employee, Contractor or Dealer, from the user's role profile and roles."""
	profile = user.get("role_profile_name")
	if profile == ADMIN_PROFILE:
		return "Admin"
	if profile == DEALER_PROFILE:
		return "Dealer"
	if profile == CONTRACTOR_PROFILE:
		return "Contractor"
	if set(_roles(user.name)) & set(ADMIN_ROLES):
		return "Admin"  # an admin by role - the company's System Manager - with no profile of his own
	# A partner by his roles: a dealer who also installs reads as a Dealer (both_kinds says so).
	kind = partner_scope.partner_kind(user.name) if user.get("enabled") else None
	return {"dealer": "Dealer", "contractor": "Contractor"}.get(kind, "Employee")


def both_kinds(name):
	"""Whether the partner is both a dealer and a contractor - he sells and installs."""
	roles = set(_roles(name))
	return {partner_scope.DEALER, partner_scope.CONTRACTOR} <= roles


#: The roles of a partner who is both: no single profile gives them.
BOTH_PARTNER_ROLES = (partner_scope.DEALER, partner_scope.CONTRACTOR)
#: The other kind a partner may also be.
OTHER_KIND = {"Dealer": "Contractor", "Contractor": "Dealer"}


def _roles(name):
	return frappe.get_all("Has Role", filters={"parent": name, "parenttype": "User"}, pluck="role")


# ------------------------------------------------------------------ an employee's roles
# An employee may do several jobs - survey and operations, say - with one login. Frappe gives a
# user the access of every role he holds at once, so he is given the roles of each job: one
# staff profile's when that is all he does, else the roles ticked one by one, with no profile.
def staff_profile_roles():
	"""{profile: [its roles, less Employee]} for the staff profiles set up on this site, in order."""
	rows = frappe.get_all("Has Role", filters={"parenttype": "Role Profile", "parent": ["in", list(STAFF_PROFILES)]},
		fields=["parent", "role"], order_by="idx asc")
	out = {p: [] for p in STAFF_PROFILES if frappe.db.exists("Role Profile", p)}
	for row in rows:
		if row.parent in out and row.role != BASE_ROLE and row.role not in out[row.parent]:
			out[row.parent].append(row.role)
	return out


def staff_roles(profiles=None):
	"""The roles an admin may tick for an employee: those of the staff profiles, in their order."""
	out = []
	for roles in (profiles or staff_profile_roles()).values():
		out.extend(r for r in roles if r not in out)
	return out


def _profile_for(roles, profiles):
	"""The staff profile whose roles are exactly these, if there is one."""
	return next((p for p, held in profiles.items() if set(held) == set(roles)), None)


def _user_roles():
	"""{user: [roles]} for every user, in one read."""
	out = {}
	for row in frappe.get_all("Has Role", filters={"parenttype": "User"}, fields=["parent", "role"], order_by="idx asc"):
		out.setdefault(row.parent, []).append(row.role)
	return out


def _scope_filters():
	"""Only the admin's own company's users: those of his tenant, where tenants are used."""
	field = _tenant_field()
	tenant = field and frappe.db.get_value("User", frappe.session.user, field)
	return {field: tenant} if tenant else {}


@frappe.whitelist()
def users(type=None, search=None):
	require_admin()
	filters = {"name": ["not in", list(HIDDEN_USERS)], "user_type": ["in", ["System User", "Website User"]]}
	filters.update(_scope_filters())
	rows = frappe.get_all("User", filters=filters, fields=["name", "full_name", "first_name", "last_name", "mobile_no",
		"enabled", "last_login", "role_profile_name", "user_type", "user_image"], order_by="enabled desc, full_name asc")
	internal = _internal_users()
	contractors = {c.user: c for c in frappe.get_all("Solar Contractor", filters={"user": ["is", "set"]},
		fields=["name", "contractor_name", "contractor_type", "user"])}
	employees = _employees()
	held_roles = _user_roles()
	tickable = set(staff_roles())
	out, counts = [], {t: 0 for t in TYPES}
	needle = (search or "").strip().lower()
	for row in rows:
		if row.name in internal:
			continue
		kind = type_of(row)
		# A website user with no partner role is a customer of the customer portal, not staff.
		if row.user_type == "Website User" and kind == "Employee":
			continue
		counts[kind] += 1
		if type and type != kind:
			continue
		if needle and needle not in " ".join(filter(None, [row.full_name, row.name, row.mobile_no])).lower():
			continue
		con = contractors.get(row.name)
		emp = employees.get(row.name) or {}
		out.append({
			"name": row.name, "full_name": row.full_name or row.name, "first_name": row.first_name or "",
			"last_name": row.last_name or "", "mobile_no": row.mobile_no or "", "enabled": cint(row.enabled),
			"type": kind, "profile": row.role_profile_name or "",
			"also": OTHER_KIND.get(kind, "") if kind in OTHER_KIND and {partner_scope.DEALER, partner_scope.CONTRACTOR}
				<= set(held_roles.get(row.name, [])) else "",
			"roles": [r for r in held_roles.get(row.name, []) if r in tickable],
			"other_roles": [r for r in held_roles.get(row.name, []) if r not in tickable and r != BASE_ROLE
				and r not in partner_scope.AUTOMATIC_ROLES],
			"contractor": {"name": con.name, "contractor_name": con.contractor_name, "contractor_type": con.contractor_type}
				if con else None,
			"last_login": format_datetime(row.last_login, "d MMM yyyy") if row.last_login else "",
			"is_me": row.name == frappe.session.user,
			"employee": emp.get("name"), "designation": emp.get("designation") or "",
			"department": emp.get("department") or "", "department_name": emp.get("department_name") or "",
		})
	return {"users": out, "counts": counts, "total": sum(counts.values())}


# ------------------------------------------------------------------ designation and department
#: The kinds of user who are the company's own staff: their job title and department are on
#: their Employee record, which Assign To reads (api/assignments.designation_of).
STAFF_TYPES = ("Admin", "Employee")


def _employees():
	"""{user: {name, designation, department, department_name}} of every Employee with a login."""
	names = dict(frappe.get_all("Department", fields=["name", "department_name"], as_list=True))
	return {e.user_id: {**e, "department_name": names.get(e.department) or e.department or ""} for e in frappe.get_all(
		"Employee", filters={"user_id": ["is", "set"]}, fields=["name", "user_id", "designation", "department"],
		order_by="status asc, creation desc")}


def _departments(company):
	return [{"value": d.name, "label": d.department_name or d.name} for d in frappe.get_all("Department",
		filters={"is_group": 0, "disabled": 0}, fields=["name", "department_name", "company"], order_by="department_name asc")
		if not company or not d.company or d.company == company]


def _employee_of(user):
	return frappe.db.get_value("Employee", {"user_id": user}, "name", order_by="status asc, creation desc") if user else None


def _check_new_employee(data, user=None):
	"""A designation or department for someone with no Employee record makes one, which needs
	his gender and date of birth: asked for before anything is saved."""
	if data.type not in STAFF_TYPES or not (data.get("designation") or data.get("department")) or _employee_of(user):
		return
	missing = [label for key, label in (("gender", _("gender")), ("date_of_birth", _("date of birth")))
		if not data.get(key)]
	if missing:
		frappe.throw(_("{0} has no Employee record yet, so one is made for the designation and department: "
			"enter the {1}.").format(" ".join(filter(None, [data.first_name, data.last_name])) or user,
			_(" and ").join(missing)))


def _save_employee(user, data, company):
	"""The staff member's designation and department, on his Employee record: the one his login
	is on, or - when either is chosen and he has none - a new one, which needs his gender, date
	of birth and joining date."""
	designation, department = (data.get("designation") or "").strip(), (data.get("department") or "").strip()
	if designation and not frappe.db.exists("Designation", designation):
		frappe.throw(_("{0} is not a designation. Add it under Designation first.").format(designation))
	if department and not frappe.db.exists("Department", department):
		frappe.throw(_("{0} is not a department.").format(department))
	name = _employee_of(user.name)
	if name:
		emp = frappe.get_doc("Employee", name)
		if (emp.designation or "", emp.department or "") == (designation, department):
			return name
		emp.designation, emp.department = designation or None, department or None
		emp.flags.ignore_permissions = True
		emp.save(ignore_permissions=True)
		return name
	if not (designation or department):
		return None
	_check_new_employee(data, user.name)
	emp = frappe.get_doc({"doctype": "Employee", "first_name": user.first_name, "last_name": user.last_name,
		"gender": data.gender, "date_of_birth": data.date_of_birth,
		"date_of_joining": data.get("date_of_joining") or frappe.utils.today(), "company": company,
		"status": "Active", "user_id": user.name, "cell_number": user.mobile_no, "designation": designation or None,
		"department": department or None})
	emp.insert(ignore_permissions=True)
	return emp.name


@frappe.whitelist()
def options():
	require_admin()
	profile_roles = staff_profile_roles()
	profiles = list(profile_roles)
	contractors = frappe.get_all("Solar Contractor", filters={"is_active": 1},
		fields=["name", "contractor_name", "contractor_type", "user", "mobile_no", "email_id"], order_by="contractor_name asc")
	from a3_sola.api.portal_share import _outgoing_account

	company = _company()
	return {"types": list(TYPES), "profiles": profiles, "profile_roles": profile_roles,
		"roles": staff_roles(profile_roles), "contractors": contractors,
		"contractor_types": list(CONTRACTOR_TYPES), "can_email": bool(_outgoing_account("User")),
		"login_url": get_url(LOGIN_PATH), "staff_types": list(STAFF_TYPES),
		"designations": frappe.get_all("Designation", pluck="name", order_by="name asc"),
		"departments": _departments(company), "genders": frappe.get_all("Gender", pluck="name", order_by="name asc"),
		"today": frappe.utils.today()}


# ------------------------------------------------------------------ saving
def _company():
	companies = get_permitted_companies(frappe.session.user)
	if companies:
		return companies[0]
	return frappe.defaults.get_user_default("company") or frappe.defaults.get_global_default("company") or \
		frappe.db.get_value("Company", {}, "name")


def _clean(data):
	data = frappe._dict(json.loads(data) if isinstance(data, str) else (data or {}))
	for key in ("first_name", "last_name", "email", "mobile_no", "type", "profile", "designation", "department",
			"gender", "date_of_birth", "date_of_joining"):
		data[key] = (data.get(key) or "").strip()
	data.email = data.email.lower()
	if data.type not in TYPES:
		frappe.throw(_("Choose the kind of user: Admin, Employee, Contractor or Dealer."))
	if not data.first_name:
		frappe.throw(_("Enter the user's first name."))
	if data.type == "Employee" and data.profile and data.profile not in STAFF_PROFILES:
		frappe.throw(_("Choose the employee's access (role profile)."))
	# Roles ticked one by one (the form sends them); None when the caller sent only a profile.
	roles = data.get("roles")
	if isinstance(roles, str):
		roles = json.loads(roles) if roles.strip().startswith("[") else [r for r in roles.split(",")]
	data.roles = None if roles is None else list(dict.fromkeys((r or "").strip() for r in roles if (r or "").strip()))
	return data


def _employee_access(data):
	"""(profile, roles) for an employee from the roles ticked: the staff profile when they are
	exactly one profile's, else no profile and the roles themselves. (None, None) when no roles
	were sent, so the profile picked - or the access he has - stands."""
	if data.roles is None:
		return data.profile or None, None
	profiles = staff_profile_roles()
	allowed = staff_roles(profiles)
	unknown = [r for r in data.roles if r not in allowed]
	if unknown:
		frappe.throw(_("{0} cannot be given here.").format(", ".join(unknown)))
	if not data.roles:
		return None, []  # none of these: only the roles he was given in the desk, if any, stay
	ordered = [r for r in allowed if r in data.roles]
	profile = _profile_for(ordered, profiles)
	if profile and not _desk_roles(data.get("name")):
		return profile, None
	return None, ordered


def _desk_roles(user):
	"""The roles an employee was given outside this page (in the desk): kept when his access
	changes, so he is then given roles rather than a profile, which would replace them."""
	if not user or not frappe.db.exists("User", user):
		return []
	current = frappe.db.get_value("User", user, ["name", "role_profile_name", "enabled"], as_dict=True)
	if current.role_profile_name or type_of(current) != "Employee":
		return []
	tickable = set(staff_roles())
	return [r for r in _roles(user) if r not in tickable and r != BASE_ROLE and r not in partner_scope.AUTOMATIC_ROLES]


def _link_contractor(email, data, company):
	"""The contractor's own record, its Portal User this login: one picked, or one made now."""
	frappe.db.sql("update `tabSolar Contractor` set user = null where user = %s", email)  # one record per login
	name = data.get("contractor")
	if not name:
		c = data.get("new_contractor") or {}
		contractor_name = (c.get("contractor_name") or "").strip() or " ".join(filter(None, [data.first_name, data.last_name]))
		doc = frappe.get_doc({"doctype": "Solar Contractor", "contractor_name": contractor_name,
			"contractor_type": c.get("contractor_type") if c.get("contractor_type") in CONTRACTOR_TYPES else "Electrical",
			"is_active": 1, "contact_person": " ".join(filter(None, [data.first_name, data.last_name])),
			"mobile_no": data.mobile_no or None, "email_id": email, "company": company})
		doc.insert(ignore_permissions=True)
		name = doc.name
	elif not frappe.db.exists("Solar Contractor", name):
		frappe.throw(_("No such contractor: {0}.").format(name))
	other = frappe.db.get_value("Solar Contractor", name, "user")
	if other and other != email:
		frappe.throw(_("{0} is already the portal login of {1}.").format(other, name))
	frappe.db.set_value("Solar Contractor", name, "user", email)
	return name


@frappe.whitelist(methods=["POST"])
def save_user(data, name=None):
	"""A new user, or changes to one. The e-mail is the login and stays as it is once made."""
	require_admin()
	from a3_sola.api.tenant_users import _set_default_company, ensure_company_permission

	data = _clean(data)
	roles = None  # an employee's own roles, when they are no one profile's
	if data.type == "Employee":
		data.name = name
		profile, roles = _employee_access(data)
		data.profile = profile or ""
	else:
		profile = PROFILE_OF[data.type]
	# A partner who is both a dealer and a contractor: his two roles, no profile.
	partner_both = data.type in OTHER_KIND and cint(data.get("also"))
	if partner_both:
		profile = None
	if name and roles is None and not partner_both:
		# Kept as they are: an admin by role (no profile), or an employee whose access was not
		# changed - setting a profile replaces every role the user holds.
		current = frappe.db.get_value("User", name, ["name", "role_profile_name", "enabled"], as_dict=True) or {}
		was = type_of(frappe._dict(current)) if current else None
		if (data.type == "Admin" and was == "Admin" and current.get("role_profile_name") != ADMIN_PROFILE) or \
				(data.type == "Employee" and was == "Employee" and not data.profile):
			profile = None
	elif not name and data.type == "Employee" and not profile and not roles:
		frappe.throw(_("Tick at least one role for the employee."))
	if profile and not frappe.db.exists("Role Profile", profile):
		frappe.throw(_("The {0} access is not set up on this site.").format(profile))
	_check_new_employee(data, name)
	company = _company()
	if name:
		if name in HIDDEN_USERS or not frappe.db.exists("User", name):
			frappe.throw(_("No such user."), frappe.DoesNotExistError)
		user = frappe.get_doc("User", name)
		if name == frappe.session.user and (data.type != "Admin" or not cint(data.get("enabled", 1))):
			frappe.throw(_("You cannot take away your own admin access, or disable yourself."))
	else:
		if not frappe.utils.validate_email_address(data.email):
			frappe.throw(_("Enter a valid e-mail address."))
		if frappe.db.exists("User", data.email):
			frappe.throw(_("{0} is already a user.").format(data.email))
		user = frappe.new_doc("User")
		user.email = data.email
		user.send_welcome_email = 0
		user.flags.no_welcome_mail = True
		field = _tenant_field()
		tenant = field and frappe.db.get_value("User", frappe.session.user, field)
		if tenant:
			user.set(field, tenant)
	user.first_name, user.last_name = data.first_name, data.last_name or None
	user.mobile_no = data.mobile_no or None
	user.enabled = cint(data.get("enabled", 1))
	if profile:
		user.role_profile_name = profile
	elif partner_both:
		user.role_profile_name = None
		user.set("roles", [])
		user.append_roles(*BOTH_PARTNER_ROLES)
	elif roles is not None:
		# Several jobs: no profile (it would replace the roles on save), and the ticked roles.
		# Roles given outside this page - in the desk - stay, while he was an employee already.
		tickable = set(staff_roles())
		was_employee = bool(name) and type_of(frappe._dict(name=name, role_profile_name=user.role_profile_name,
			enabled=1)) == "Employee"
		kept = [r.role for r in user.get("roles") if r.role not in tickable] if was_employee else []
		if not roles and not set(kept) - {BASE_ROLE} - partner_scope.AUTOMATIC_ROLES:
			frappe.throw(_("Tick at least one role for the employee."))
		user.role_profile_name = None
		user.set("roles", [])
		user.append_roles(*dict.fromkeys(kept + [BASE_ROLE] + roles))
	user.flags.ignore_permissions = True
	frappe.db.savepoint("portal_user")
	try:
		user.save(ignore_permissions=True) if name else user.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		# The mobile number is another user's: kept off this one rather than refusing him.
		frappe.db.rollback(save_point="portal_user")
		user.mobile_no = None
		user.save(ignore_permissions=True) if name else user.insert(ignore_permissions=True)
		frappe.msgprint(_("{0} is another user's mobile number, so it was not saved on this one.").format(data.mobile_no),
			indicator="orange", alert=True)
	if company:
		ensure_company_permission(user.name, company)
		_set_default_company(user.name, company)
	employee = _save_employee(user, data, company) if data.type in STAFF_TYPES else None
	contractor = None
	if data.type == "Contractor" or partner_both:
		contractor = _link_contractor(user.name, data, company)
	else:
		frappe.db.sql("update `tabSolar Contractor` set user = null where user = %s", user.name)
	frappe.clear_cache(user=user.name)
	return {"name": user.name, "created": not name, "contractor": contractor, "employee": employee,
		"user": next((u for u in users()["users"] if u["name"] == user.name), None)}


def _user(name):
	require_admin()
	if not name or name in HIDDEN_USERS or not frappe.db.exists("User", name):
		frappe.throw(_("No such user."), frappe.DoesNotExistError)
	return frappe.get_doc("User", name)


@frappe.whitelist(methods=["POST"])
def set_enabled(name, enabled):
	user = _user(name)
	if name == frappe.session.user:
		frappe.throw(_("You cannot disable yourself."))
	user.enabled = cint(enabled)
	user.flags.ignore_permissions = True
	user.save(ignore_permissions=True)
	if not user.enabled:
		frappe.sessions.clear_sessions(user=name, force=True)
	return {"name": name, "enabled": user.enabled}


@frappe.whitelist(methods=["POST"])
def delete_user(name):
	"""Deleted if nothing in the system names the user; else disabled, so the records he made
	keep who made them."""
	user = _user(name)
	if name == frappe.session.user:
		frappe.throw(_("You cannot delete yourself."))
	frappe.db.savepoint("portal_user_delete")
	try:
		frappe.db.sql("update `tabSolar Contractor` set user = null where user = %s", name)
		frappe.delete_doc("User", name, ignore_permissions=True)
		frappe.db.delete("DefaultValue", {"parent": name})
		return {"deleted": 1}
	except (frappe.LinkExistsError, frappe.ValidationError):
		frappe.db.rollback(save_point="portal_user_delete")
		frappe.clear_messages()
		user = frappe.get_doc("User", name)
		user.enabled = 0
		user.flags.ignore_permissions = True
		user.save(ignore_permissions=True)
		frappe.sessions.clear_sessions(user=name, force=True)
		return {"deleted": 0, "disabled": 1,
			"message": _("{0} is named in records in the system, so the user was disabled instead of deleted. "
				"They can no longer sign in.").format(user.full_name or name)}


# ------------------------------------------------------------------ passwords and the welcome
def _set_password_link(user):
	"""A one-time link to the portal's own set-password page (Frappe's key, hashed as it expects)."""
	link = user._reset_password(send_email=False)
	key = link.split("key=", 1)[1].split("&", 1)[0]
	return get_url(f"{SET_PASSWORD_PATH}?key={key}")


@frappe.whitelist(methods=["POST"])
def password_link(name):
	user = _user(name)
	return {"link": _set_password_link(user), "hours": cint(frappe.db.get_single_value("System Settings",
		"reset_password_link_expiry_duration") or 0) // 3600 or None}


@frappe.whitelist(methods=["POST"])
def set_password(name, password):
	"""A password the admin chooses - to be changed by the user - after Frappe's strength check."""
	from frappe.utils.password import update_password
	from frappe.utils.password_strength import test_password_strength

	user = _user(name)
	password = password or ""
	if len(password) < 8:
		frappe.throw(_("Use at least 8 characters."))
	# The site's own password policy, as Frappe applies it when a user sets one himself.
	if cint(frappe.db.get_single_value("System Settings", "enable_password_policy")):
		minimum = cint(frappe.db.get_single_value("System Settings", "minimum_password_score")) or 2
		result = test_password_strength(password, [user.first_name, user.last_name, user.name])
		if cint(result.get("score")) < minimum:
			warning = (result.get("feedback") or {}).get("warning")
			frappe.throw(_("That password is too weak. {0}").format(warning or _("Choose a longer, less common one.")))
	update_password(user.name, password)
	frappe.sessions.clear_sessions(user=user.name, force=True)
	return {"name": user.name}


def welcome_text(user, link):
	from a3_sola.api.portal_share import DEFAULT_SENDER, SIGNATURE

	first = user.first_name or user.full_name or ""
	company = _company() or "Renewcore Innovations LLP"
	return "\n".join([
		_("Hi {0},").format(first), "",
		_("Your account on the {0} portal is ready.").format(company), "",
		_("*Sign in:* {0}").format(get_url(LOGIN_PATH)),
		_("*Login:* {0}").format(user.name), "",
		_("Set your password here first (the link works once):"), link, "",
		SIGNATURE.format(sender=DEFAULT_SENDER[0], phone=DEFAULT_SENDER[1]),
	])


@frappe.whitelist(methods=["POST"])
def welcome(name, channel="whatsapp"):
	"""The welcome - the sign-in address, the login and a set-password link - as a WhatsApp link
	to the user's mobile, or sent by e-mail."""
	user = _user(name)
	link = _set_password_link(user)
	text = welcome_text(user, link)
	if channel == "email":
		from a3_sola.api.portal_share import _as_html, _outgoing_account

		account = _outgoing_account("User")
		if not account:
			frappe.throw(_("No mailbox is set up to send from. Set up the company's outgoing e-mail account in "
				"ERPNext, or send the welcome on WhatsApp."), title=_("E-mail Not Set Up"))
		frappe.sendmail(recipients=[user.name], sender=account.email_id, subject=_("Your portal account"),
			message=_as_html(text), now=True)
		sent = {"sent": 1}
	else:
		from a3_sola.api.outreach import whatsapp_link

		sent = {"whatsapp": whatsapp_link(user.mobile_no, text), "has_mobile": bool(user.mobile_no)}
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "User", "reference_name": user.name,
		"content": _("Welcome sent by {0} ({1}).").format(channel, frappe.session.user)}).insert(ignore_permissions=True)
	return sent | {"link": link, "text": text}
