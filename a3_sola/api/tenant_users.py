# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Creating the people who will use a tenant. Past the point of no return.

Two decisions in here are worth stating plainly, because both look like unhelpful strictness
until you consider what the alternative does.

**No password is ever set by the system.** Not a generated one, not a temporary one, not
one emailed in plaintext. The user is created with no password and a single-use reset link
goes to the address Phase 4 already verified. A system that can set a password is a system
whose logs, backups and support tooling all contain passwords.

**An existing email address fails the step rather than reusing the account.** It is a
plausible situation - somebody signs up twice, or a consultant runs several tenants - and
the tempting behaviour is to attach the existing user to the new tenant. That is a
cross-tenant access bug with a friendly face: one login, two companies, and a User
Permission set that nobody audits afterwards. So it stops and asks a human.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from a3_sola.api.entitlements import INTERNAL_PLATFORM_ROLES, TENANT_FIELD, forbidden_roles
from a3_sola.api.settings import get_int, get_value

#: What a tenant admin gets on your side of the fence: their own billing, and nothing else.
TENANT_ADMIN_PLATFORM_ROLES = ("Customer",)


# ------------------------------------------------------------------- step 09
def create_admin_user(context):
	tenant = context.reload_tenant()
	email = (tenant.primary_contact_email or "").strip().lower()
	if not email:
		frappe.throw(_("The tenant has no contact email, so there is no administrator to create."))

	if tenant.admin_user and frappe.db.exists("User", tenant.admin_user):
		return {"created_doctype": "User", "created_name": tenant.admin_user,
		        "remarks": "already existed"}

	if frappe.db.exists("User", email):
		frappe.throw(
			_("A user account already exists for {0}. Provisioning will not attach an "
			  "existing account to a new tenant: one login across two tenants is a "
			  "cross-tenant access problem, not a convenience. Decide deliberately - "
			  "either use a different administrator address for {1}, or move the existing "
			  "account after checking what it can already see.").format(
				frappe.bold(email), frappe.bold(tenant.tenant_name)
			),
			title=_("Email Already In Use"),
		)

	first_name, last_name = _split_name(tenant.primary_contact_name or email.split("@")[0])

	# Tells the quota hook that this particular user is the tenant's own admin and must be
	# allowed through whatever the arithmetic says.
	frappe.flags.a3s_provisioning_admin = email
	frappe.db.savepoint("admin_user")
	try:
		user = _insert_admin(tenant, email, first_name, last_name, with_mobile=True)
		if user is None:
			# Frappe makes `mobile_no` unique across the whole instance. Two tenants can
			# legitimately share a number - a consultant running several, a family
			# business - and a phone number is a convenience field, not identity. The
			# email is the identity, and that was already checked explicitly above. So the
			# number is dropped rather than the provisioning failed.
			context.note(
				f"The phone number on {email} is already held by another user, so it was "
				f"left off this account. The address itself is unique."
			)
			user = _insert_admin(tenant, email, first_name, last_name, with_mobile=False)
	finally:
		frappe.flags.a3s_provisioning_admin = None

	# Deliberately never `user.new_password = ...`. See the module docstring.
	tenant.db_set("admin_user", user.name, update_modified=False)
	context.admin_user = user.name
	context.record("09_CREATE_ADMIN_USER", "User", user.name)
	context.artefacts["password_reset_link"] = password_reset_link(user.name)
	return {"created_doctype": "User", "created_name": user.name}


def _insert_admin(tenant, email, first_name, last_name, with_mobile):
	"""Insert the admin user. Returns None when only the phone number was in the way."""
	user = frappe.new_doc("User")
	user.update(
		{
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"user_type": "System User",
			"enabled": 1,
			"send_welcome_email": 0,  # our own welcome goes out at step 13
			"language": "en",
			TENANT_FIELD: tenant.name,
		}
	)
	if with_mobile and tenant.primary_contact_phone:
		user.mobile_no = tenant.primary_contact_phone
	if cint(get_value("enable_two_factor_for_admins")):
		user.two_factor_authentication = 1
	user.flags.ignore_permissions = True
	user.flags.no_welcome_mail = True
	try:
		user.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		if not with_mobile:
			raise
		frappe.db.rollback(save_point="admin_user")
		return None
	return user


def password_reset_link(email):
	"""A single-use link with the configured expiry. Delivered only to the verified address."""
	hours = get_int("password_link_expiry_hours", 72) or 72
	user = frappe.get_doc("User", email)
	key = frappe.generate_hash()
	user.db_set("reset_password_key", key, update_modified=False)
	user.db_set("last_reset_password_key_generated_on", now_datetime(), update_modified=False)
	return {
		"url": frappe.utils.get_url(f"/update-password?key={key}"),
		"expires_in_hours": hours,
	}


# ------------------------------------------------------------------- step 10
def assign_admin_permissions(context):
	tenant = context.reload_tenant()
	email = tenant.admin_user
	if not email:
		frappe.throw(_("There is no administrator to assign permissions to."))
	company = tenant.company
	if not company:
		frappe.throw(_("The tenant has no company, so there is nothing to confine the user to."))

	profile = tenant.assigned_role_profile or get_value("admin_role_profile_fallback")
	roles = _roles_for(tenant, profile)
	apply_roles(email, roles)

	# THE record the whole permission layer depends on. Created, then read back, because
	# a missing one means this user sees every tenant on the instance.
	permission = ensure_company_permission(email, company)
	if not frappe.db.exists("User Permission", permission):
		frappe.throw(
			_("The company User Permission for {0} could not be verified after creation. "
			  "Without it this user would see every tenant on the instance.").format(email),
			title=_("Isolation Not Established"),
		)

	_set_default_company(email, company)
	frappe.db.set_value("User", email, TENANT_FIELD, tenant.name, update_modified=False)
	_append_tenant_user(tenant, email, profile, is_admin=True)

	held = set(frappe.get_roles(email))
	leaked = held & set(forbidden_roles(tenant.name))
	if leaked:
		frappe.throw(
			_("The tenant administrator holds roles their plan does not include: {0}").format(
				", ".join(sorted(leaked))
			),
			title=_("Entitlement Violation"),
		)

	context.record("10_ASSIGN_PERMISSIONS", "User Permission", permission)
	return {
		"created_doctype": "User Permission",
		"created_name": permission,
		"remarks": _("{0} roles assigned, confined to {1}.").format(len(roles), company),
	}


def _roles_for(tenant, profile):
	"""The roles a tenant admin gets: their plan's modules, plus their own billing page.

	Never an internal Platform role. That boundary is between your customer and your own
	business data, and there is a test that asserts it.
	"""
	forbidden = forbidden_roles(tenant.name)
	roles = set()
	if profile and frappe.db.exists("Role Profile", profile):
		roles |= {row.role for row in frappe.get_cached_doc("Role Profile", profile).roles}
	from a3_sola.api.entitlements import MODULE_ROLES, enabled_modules

	for module in enabled_modules(tenant.name):
		roles |= set(MODULE_ROLES.get(module, ()))
	roles |= set(TENANT_ADMIN_PLATFORM_ROLES)
	roles -= forbidden
	roles -= set(INTERNAL_PLATFORM_ROLES)
	return sorted(role for role in roles if frappe.db.exists("Role", role))


def apply_roles(email, roles):
	user = frappe.get_doc("User", email)
	existing = {row.role for row in user.roles}
	for role in roles:
		if role not in existing:
			user.append("roles", {"role": role})
	user.flags.ignore_permissions = True
	user.flags.a3s_skip_quota = True
	user.save(ignore_permissions=True)
	return roles


def ensure_company_permission(email, company):
	existing = frappe.db.get_value(
		"User Permission", {"user": email, "allow": "Company", "for_value": company}, "name"
	)
	if existing:
		return existing
	permission = frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": email,
			"allow": "Company",
			"for_value": company,
			"apply_to_all_doctypes": 1,
			"is_default": 1,
		}
	)
	permission.flags.ignore_permissions = True
	permission.insert(ignore_permissions=True)
	return permission.name


def _set_default_company(email, company):
	"""Set the user's default company under the key Frappe actually reads.

	`frappe.defaults.get_user_default("Company")` does not read a row stored as `Company`.
	For a key that is also a user-permission key it deliberately looks up the *scrubbed*
	name - `company` - and falls back to the site-wide default when that is missing. So a
	default stored under `Company` is invisible, and the tenant admin's desk opens on
	whichever company happens to be the global default. That looks exactly like an
	isolation failure to whoever reports it.

	Storing the right key is not enough on its own either: MariaDB compares strings
	case-insensitively, so Frappe's own "does this default already exist" check matches
	`Company` when asked about `company` and updates that row instead of adding one. Any
	stale row therefore has to go first.
	"""
	frappe.db.delete("DefaultValue", {"parent": email, "defkey": ["in", ["Company", "company"]]})
	frappe.defaults.set_user_default("company", company, email)
	frappe.clear_cache(user=email)


def _append_tenant_user(tenant, email, profile, is_admin=False, source="Provisioning"):
	if any(row.user == email for row in tenant.users):
		return
	tenant.append(
		"users",
		{
			"user": email,
			"full_name": frappe.db.get_value("User", email, "full_name"),
			"role_profile": profile,
			"is_admin": cint(is_admin),
			"enabled": 1,
			"added_on": now_datetime(),
			"source": source,
		},
	)
	tenant.flags.ignore_permissions = True
	tenant.flags.ignore_validate_update_after_submit = True
	tenant.save(ignore_permissions=True)


def _split_name(full_name):
	parts = [p for p in (full_name or "").split() if p]
	if not parts:
		return "User", ""
	if len(parts) == 1:
		return parts[0][:60], ""
	return parts[0][:60], " ".join(parts[1:])[:60]


def provision_invited_user(invitation):
	"""Create a user from an accepted invitation, with exactly step 10's permissions."""
	tenant = frappe.get_doc("Tenant", invitation.tenant)
	email = (invitation.invited_email or "").strip().lower()
	first_name, last_name = _split_name(invitation.invited_name or email.split("@")[0])

	user = frappe.new_doc("User")
	user.update(
		{
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"user_type": "System User",
			"enabled": 1,
			"send_welcome_email": 0,
			TENANT_FIELD: tenant.name,
		}
	)
	user.flags.ignore_permissions = True
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)

	profile = invitation.role_profile or tenant.assigned_role_profile
	apply_roles(email, _roles_for(tenant, profile))
	ensure_company_permission(email, tenant.company)
	_set_default_company(email, tenant.company)
	_append_tenant_user(tenant, email, profile, is_admin=False, source="Invitation")
	return user.name
