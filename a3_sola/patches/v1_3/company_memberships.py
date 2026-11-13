# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every existing login's company, written down as its Company Membership. Changes no one.

Each user who is confined to exactly one company gets a membership there holding exactly
the roles they hold now, and that company is set as the one they are working in. Nothing
is applied - roles, permissions and defaults are already what the membership says - so
the patch cannot change what anybody sees.

Not touched:

* Administrator, Guest, platform staff and anyone holding System Manager *without* a
  company permission: they are not confined to a company and never switch.
* Anyone with permissions on several companies today: listed in the Error Log for an
  admin to decide, rather than guessed at.

Run `report()` first (System Console or bench execute) to see what it would do.
"""

import frappe

DOCTYPE = "Company Membership"


def plan():
	"""(one company: [(user, company)], several: [(user, [companies])])."""
	rows = frappe.db.sql(
		"""select user, group_concat(for_value order by for_value separator '\\n') companies, count(*) n
		from `tabUser Permission` where allow = 'Company' and user not in ('Administrator', 'Guest')
		group by user""",
		as_dict=True,
	)
	single, several = [], []
	for row in rows:
		if not frappe.db.exists("User", row.user):
			continue
		companies = row.companies.split("\n")
		if row.n == 1:
			single.append((row.user, companies[0]))
		else:
			several.append((row.user, companies))
	return single, several


def report():
	single, several = plan()
	done = set(frappe.get_all(DOCTYPE, pluck="user")) if frappe.db.table_exists(DOCTYPE) else set()
	return {
		"memberships_to_create": [u for u, _c in single if u not in done],
		"already_have_one": sorted(done),
		"several_companies_left_alone": several,
	}


def execute():
	from a3_sola.api import memberships

	from a3_sola.setup.install import install_custom_fields

	frappe.reload_doc("platform", "doctype", "company_membership_role")
	frappe.reload_doc("platform", "doctype", "company_membership")
	install_custom_fields()  # User "Working In" - patches run before after_migrate installs it
	frappe.db.add_unique(DOCTYPE, ["user", "company"], constraint_name="unique_user_company")
	_settings_defaults()
	single, several = plan()
	frappe.flags.a3s_migrating = True
	try:
		for user, company in single:
			if frappe.db.exists(DOCTYPE, {"user": user}):
				continue
			memberships.record_current(user, company, source="Migration")
	finally:
		frappe.flags.a3s_migrating = False
	if several:
		frappe.log_error(
			title="a3_sola: logins with several companies left as they are",
			message="These logins hold permissions on more than one company. They keep seeing all of them "
			"until an admin gives each company a Company Membership:\n\n"
			+ "\n".join(f"{u}: {', '.join(c)}" for u, c in several),
		)
	# Seat counts now come from memberships: recount, and say so if any tenant's changed.
	from a3_sola.api.entitlements import recalculate_usage

	changed = []
	for tenant in frappe.get_all("Tenant", fields=["name", "active_users"]):
		after = recalculate_usage(tenant.name)["used"]
		if after != (tenant.active_users or 0):
			changed.append(f"{tenant.name}: {tenant.active_users} -> {after}")
	if changed:
		frappe.log_error(title="a3_sola: seat counts changed when memberships were recorded",
			message="\n".join(changed))


#: New A3 Sola Settings fields, with their defaults: a new field of a Single holds no value
#: until it is saved, and reads as 0 - which would switch these off.
SETTINGS_DEFAULTS = {
	"allow_shared_logins": 1,
	"notify_user_on_impersonation": 1,
	"company_admin_impersonation_enabled": 1,
	"company_admin_impersonation_max_minutes": 60,
	"impersonation_max_minutes": 120,
}


def _settings_defaults():
	frappe.reload_doc("solar_crm", "doctype", "a3_sola_settings")
	for field, value in SETTINGS_DEFAULTS.items():
		stored = frappe.db.sql("select 1 from `tabSingles` where doctype = 'A3 Sola Settings' and field = %s", field)
		if not stored:
			frappe.db.set_single_value("A3 Sola Settings", field, value)
