# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Making a seat count mean something.

ERPNext has no idea that a Company may have five users. Selling seats without enforcing
them means every tenant eventually has forty people on a five-seat plan, and you find out
during a renewal conversation - which is the worst possible time, because by then taking
the seats away is a fight rather than a setting.

So enforcement is a hard block at the moment a user is created, invited, or re-enabled.
Not a nightly report. A report tells you about the problem after the customer has built
their process around it.

The other half matters just as much: **it must never lock a tenant out of their own admin
account.** A quota arithmetic bug that blocks the Administrator, or the tenant admin, or a
*disable* operation, turns a billing feature into an outage. The exemptions below are not
loopholes - they are the difference between a guard and a hazard.

Everything here reads the Tenant's **snapshot**. Never the live Subscription Plan. If the
Starter plan becomes eight users tomorrow, existing Starter tenants keep the five they
bought until somebody explicitly changes their plan.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

TENANT_FIELD = "a3_sola_tenant"

#: Roles that belong to your own business, never to a customer.
INTERNAL_PLATFORM_ROLES = (
	"Platform Admin",
	"Platform Sales",
	"Platform Marketing Manager",
	"Platform Billing Executive",
	"Platform Billing Manager",
	"Platform Provisioning Operator",
	"Platform Tenant Manager",
)

#: Which roles belong to which sellable module. A user of a tenant without a module must
#: not hold any of its roles - that is the whole of module gating.
MODULE_ROLES = {
	"Solar CRM": (
		"Solar Sales Executive", "Solar Survey Engineer", "Solar Design Engineer",
		"Solar Sales Manager", "Solar CRM Manager",
	),
	"Solar Operations": (
		"Solar Operations Executive", "Solar Site Engineer", "Solar Documentation Officer",
		"Solar Liaison Officer", "Solar Operations Manager", "Solar QC Inspector",
		"Solar Technician",
	),
	"Solar Projects": (
		"Solar Project Manager", "Solar Accounts Executive", "Solar O&M Manager",
		"Solar Service Coordinator", "Solar Service Technician",
	),
}

MODULE_WORKSPACES = {
	"Solar CRM": "Solar CRM",
	"Solar Operations": "Solar Operations",
	"Solar Projects": "Solar Projects",
}


# ------------------------------------------------------------------- step 08
def apply_to_tenant(context):
	"""Write the entitlement snapshot into enforceable form."""
	tenant = context.reload_tenant()
	entitlements = context.entitlements or {}
	if entitlements:
		tenant.db_set(
			{
				"user_quota": cint(entitlements.get("user_quota")),
				"max_companies": cint(entitlements.get("max_companies")) or 1,
				"storage_limit_gb": cint(entitlements.get("storage_limit_gb")),
				"assigned_role_profile": entitlements.get("assigned_role_profile"),
			},
			update_modified=False,
		)
	recalculate_usage(tenant.name)
	context.reload_tenant()
	return {
		"created_doctype": "Entitlements",
		"created_name": tenant.name,
		"remarks": _("Quota {0} seats; modules: {1}.").format(
			cint(tenant.user_quota), ", ".join(context.enabled_module_names()) or "none"
		),
	}


def clear_applied(context):
	tenant = context.reload_tenant()
	if tenant:
		tenant.db_set({"seats_available": 0, "active_users": 0, "pending_invitations": 0},
		              update_modified=False)


# --------------------------------------------------------------------- usage
def get_tenant_usage(tenant_name):
	"""Seats used, pending and available. The one place the arithmetic lives."""
	quota = cint(frappe.db.get_value("Tenant", tenant_name, "user_quota"))
	used = frappe.db.count(
		"User", {TENANT_FIELD: tenant_name, "enabled": 1, "user_type": "System User"}
	)
	pending = frappe.db.count(
		"Tenant Invitation", {"tenant": tenant_name, "status": ["in", ["Pending", "Sent"]]}
	)
	return {
		"quota": quota,
		"used": used,
		"pending": pending,
		"available": max(0, quota - used - pending),
		"available_ignoring_pending": max(0, quota - used),
		"over_quota": used > quota if quota else False,
	}


def recalculate_usage(tenant_name):
	usage = get_tenant_usage(tenant_name)
	frappe.db.set_value(
		"Tenant", tenant_name,
		{
			"active_users": usage["used"],
			"pending_invitations": usage["pending"],
			"seats_available": usage["available"],
			"last_usage_calculated_on": now_datetime(),
		},
		update_modified=False,
	)
	return usage


def assert_seat_available(tenant_name, for_email=None, counting_pending=True):
	"""Refuse when the tenant is full, and say so in words a customer can act on."""
	usage = get_tenant_usage(tenant_name)
	available = usage["available"] if counting_pending else usage["available_ignoring_pending"]
	if available > 0:
		return usage
	tenant_label = frappe.db.get_value("Tenant", tenant_name, "tenant_name") or tenant_name
	frappe.throw(
		_("{0} has used all {1} of its seats. To add {2}, buy more seats from your billing "
		  "page or remove a user who no longer needs access.").format(
			tenant_label, usage["quota"], for_email or _("another user")
		),
		title=_("No Seats Available"),
	)


# ---------------------------------------------------------------- user hooks
def before_user_save(doc, method=None):
	"""Block a tenant going over quota, at the moment it would happen.

	Runs on validate for every User on the instance, so the exemptions come first and are
	cheap: no tenant stamp means internal staff, and internal staff are not metered.
	"""
	if frappe.flags.in_install or frappe.flags.in_migrate:
		return
	tenant = doc.get(TENANT_FIELD)
	if not tenant:
		return
	if doc.name == "Administrator" or doc.get("__provisioning_admin"):
		return
	if frappe.flags.a3s_provisioning_admin == doc.email:
		# The tenant's own admin, created by step 09. Always allowed, even if the quota
		# arithmetic is somehow zero - a tenant locked out of its own admin account is a
		# support catastrophe, and the seat was paid for.
		return
	if not cint(doc.enabled):
		# Disabling is always allowed. A quota check that blocks somebody freeing a seat
		# would be actively harmful.
		return

	was_enabled = 1
	if not doc.is_new():
		was_enabled = cint(frappe.db.get_value("User", doc.name, "enabled"))
	if was_enabled and not doc.is_new():
		return  # already counted; nothing is being consumed

	if frappe.db.get_value("Tenant", tenant, "admin_user") == doc.email:
		return
	assert_seat_available(tenant, for_email=doc.email, counting_pending=False)


def after_user_change(doc, method=None):
	tenant = doc.get(TENANT_FIELD)
	if tenant and frappe.db.exists("Tenant", tenant):
		recalculate_usage(tenant)


# ------------------------------------------------------------ module gating
def enabled_modules(tenant_name):
	rows = frappe.get_all(
		"Tenant Module", filters={"parent": tenant_name, "parenttype": "Tenant"},
		fields=["module_name", "is_enabled"],
	)
	return [row.module_name for row in rows if cint(row.is_enabled)]


def forbidden_roles(tenant_name):
	allowed = set(enabled_modules(tenant_name))
	out = set()
	for module, roles in MODULE_ROLES.items():
		if module not in allowed:
			out.update(roles)
	out.update(INTERNAL_PLATFORM_ROLES)
	return out


def apply_module_entitlements(tenant_name):
	"""Reconcile every tenant user's roles against the snapshot. Idempotent.

	This is the whole of Phase 7's upgrade path: change the entitlement rows, call this,
	done. It is also the drift repair - run it twice and the second run changes nothing.
	Gating is by role and workspace visibility, never by deleting doctypes: a Starter
	tenant upgrading to Growth must gain Solar Projects by changing one entitlement, not
	by a migration.
	"""
	forbidden = forbidden_roles(tenant_name)
	profile = frappe.db.get_value("Tenant", tenant_name, "assigned_role_profile")
	allowed_from_profile = _profile_roles(profile) - forbidden

	changed = []
	users = frappe.get_all("User", filters={TENANT_FIELD: tenant_name}, pluck="name")
	for email in users:
		user = frappe.get_doc("User", email)
		held = {row.role for row in user.roles}
		remove = held & forbidden
		add = allowed_from_profile - held if user.email == frappe.db.get_value(
			"Tenant", tenant_name, "admin_user"
		) else set()
		if not remove and not add:
			continue
		user.roles = [row for row in user.roles if row.role not in remove]
		for role in sorted(add):
			user.append("roles", {"role": role})
		user.flags.ignore_permissions = True
		user.flags.a3s_skip_quota = True
		user.save(ignore_permissions=True)
		changed.append({"user": email, "removed": sorted(remove), "added": sorted(add)})
	return {"tenant": tenant_name, "changed": changed, "forbidden": sorted(forbidden)}


def _profile_roles(profile):
	if not profile or not frappe.db.exists("Role Profile", profile):
		return set()
	doc = frappe.get_cached_doc("Role Profile", profile)
	return {row.role for row in doc.roles}


def module_for_workspace(workspace):
	for module, name in MODULE_WORKSPACES.items():
		if name == workspace:
			return module
	return None


def tenant_of(user=None):
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return None
	return frappe.db.get_value("User", user, TENANT_FIELD)


def has_module(module, user=None):
	"""Is this module included in the viewer's plan?

	Internal staff have no tenant stamp and are therefore not gated - which is correct:
	your own people are not customers of your own plans.
	"""
	tenant = tenant_of(user)
	if not tenant:
		return True
	return module in enabled_modules(tenant)


def upgrade_message(module):
	return _(
		"{0} is not included in your current plan. Everything you have already is "
		"unaffected - adding it is a plan change you can make from your billing page."
	).format(_(module))


# ------------------------------------------------------------------- seats
def add_seats(tenant, count):
	"""Phase 7 implements this. See a3_sola/api/lifecycle/seats.py.

	The contract this stub promised is kept: the quota is re-snapshotted, prorated billing
	goes through the Phase 5 path, and `apply_module_entitlements` runs afterwards. Phase 7
	widens it in one deliberate way - a long-tenured tenant with no failed payments gets
	the seat immediately and is billed on the next invoice, because a hard quota block that
	takes three days to clear becomes a support ticket and a bad review.
	"""
	from a3_sola.api.lifecycle.seats import add_seats as implementation

	return implementation(tenant, count)


# ------------------------------------------------------------------- nightly
def recalculate_all_usage():
	"""Nightly. Corrects drift, and says so when a tenant is over its quota.

	A bug that lets one tenant past the gate should be visible the next morning rather
	than at renewal.
	"""
	over = []
	for name in frappe.get_all("Tenant", filters={"status": ["in", ["Active", "Suspended"]]},
	                           pluck="name"):
		usage = recalculate_usage(name)
		if usage["over_quota"]:
			over.append(f"{name}: {usage['used']} users on a {usage['quota']}-seat plan")
	frappe.db.commit()
	if over:
		frappe.log_error(
			title="a3_sola: tenants over their seat quota",
			message=(
				"These tenants hold more enabled users than they have paid for. Either the "
				"enforcement was bypassed or their plan changed without a re-snapshot.\n\n"
				+ "\n".join(over)
			),
		)
	return {"checked": frappe.db.count("Tenant"), "over_quota": len(over)}
