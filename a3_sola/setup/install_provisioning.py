# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Phase 6 setup: the two provisioning roles, and the blueprint every tenant starts from.

The blueprint seeded here is deliberately thin. The bulk of what a tenant gets - DISCOM,
tariffs, schemes, stage chains, document templates, packages - comes from
`setup.install.seed_masters`, the same function that seeds the first company at install
time. Reusing it is the point: a tenant provisioned in production must get exactly what a
developer's site gets, and two code paths meant to produce the same masters will have
diverged within a month.

What the blueprint adds on top is the per-tenant content somebody will want to change
without a deploy, plus the post-provision notes the admin reads on first login.
"""

import json

import frappe
from frappe.utils import cint

MODULE = "Platform"

PROVISIONING_ROLES = [
	(
		"Platform Provisioning Operator",
		"Watches provisioning jobs, resumes and retries them. Cannot terminate a tenant.",
	),
	(
		"Platform Tenant Manager",
		"Tenant management, entitlement changes, and termination with typed confirmation.",
	),
]

PROVISIONING_ROLE_PROFILES = {
	"Platform Provisioning": ["Platform Provisioning Operator"],
	"Platform Tenant Management": ["Platform Tenant Manager", "Platform Provisioning Operator"],
}

#: What a tenant admin gets on the customer side. Deliberately narrow: their own workspace
#: and their own billing, and nothing of yours.
TENANT_ADMIN_PROFILE = "Solar Tenant Administrator"
TENANT_ADMIN_ROLES = [
	"Solar CRM Manager",
	"Solar Sales Manager",
	"Solar Operations Manager",
	"Solar Project Manager",
	"Accounts Manager",
	"Customer",
]

DEFAULT_BLUEPRINT = "Standard Solar EPC Workspace"

POST_PROVISION_NOTES = """
<p>Your workspace is ready and already knows how a Kerala rooftop solar business works.
The pipeline, the nineteen execution stages, the document pack, the subsidy scheme and the
five-year O&amp;M model are all set up.</p>
<p>Four things were left for you on purpose, because guessing them would have been worse
than leaving them blank:</p>
<ul>
  <li><b>Your ledger accounts.</b> Every account mapping is empty. A guessed mapping posts
  money to the wrong ledger and nobody notices until a reconciliation.</li>
  <li><b>The electricity tariff.</b> A representative one was seeded so savings
  calculations work today. Check it against the current tariff order before you quote.</li>
  <li><b>The GST valuation.</b> The 70:30 blended rule is seeded but inactive. Your CA
  signs that off, not us.</li>
  <li><b>Your own pricing.</b> Starter packages at 1, 2, 3 and 5 kW are a starting point,
  not your price list.</li>
</ul>
"""

#: Seed items the blueprint adds on top of `seed_masters`. Kept small and data-driven so a
#: change to onboarding content is a desk edit rather than a release.
SEED_ITEMS = [
	{
		"sequence": 10,
		"seed_type": "Master Record",
		"target_doctype": "Project Type",
		"module": "Solar Projects",
		"payload": json.dumps({"project_type": "Solar Rooftop Installation"}),
		"is_mandatory": 0,
		"skip_if_exists": 1,
		"notes": "Phase 3 links projects to this type.",
	},
	{
		"sequence": 20,
		"seed_type": "Master Record",
		"target_doctype": "Opportunity Type",
		"module": "Solar CRM",
		"payload": json.dumps({"name": "Solar O&M Renewal"}),
		"is_mandatory": 0,
		"skip_if_exists": 1,
		"notes": "Renewal opportunities raised by the O&M scheduler land here.",
	},
]


def setup():
	create_roles()
	seed_default_blueprint()
	set_settings_defaults()


def create_roles():
	for role, description in PROVISIONING_ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
				"is_custom": 1,
				"search_bar": 1,
				"notifications": 1,
				"list_sidebar": 1,
				"bulk_actions": 1,
				"form_sidebar": 1,
				"timeline": 1,
				"dashboard": 1,
			}
		).insert(ignore_permissions=True)

	for profile, roles in PROVISIONING_ROLE_PROFILES.items():
		_upsert_profile(profile, roles)
	_upsert_profile(TENANT_ADMIN_PROFILE, TENANT_ADMIN_ROLES)


def _upsert_profile(profile, roles):
	available = [r for r in roles if frappe.db.exists("Role", r)]
	if not available:
		return
	if frappe.db.exists("Role Profile", profile):
		doc = frappe.get_doc("Role Profile", profile)
		existing = {row.role for row in doc.roles}
		added = False
		for role in available:
			if role not in existing:
				doc.append("roles", {"role": role})
				added = True
		if added:
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
		return
	frappe.get_doc(
		{
			"doctype": "Role Profile",
			"role_profile": profile,
			"roles": [{"role": r} for r in available],
		}
	).insert(ignore_permissions=True)


def seed_default_blueprint():
	"""Idempotent, and it never overwrites edits.

	The client will change the post-provision notes. A re-run that reset them would be
	worse than not seeding at all.
	"""
	existing = frappe.db.exists("Tenant Blueprint", {"blueprint_name": DEFAULT_BLUEPRINT})
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Tenant Blueprint",
			"blueprint_name": DEFAULT_BLUEPRINT,
			"is_default": 1,
			"is_active": 1,
			"description": (
				"Everything a Kerala rooftop solar EPC needs on day one. The module masters "
				"come from the shared seeding path; this adds the per-tenant records and the "
				"notes the admin reads first."
			),
			"post_provision_notes": POST_PROVISION_NOTES,
			"seed_items": [
				item for item in SEED_ITEMS
				if frappe.db.exists("DocType", item["target_doctype"])
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def set_settings_defaults():
	"""Point the fallback role profile and the failure-notification role at real records."""
	settings = frappe.get_single("A3 Sola Settings")
	changed = False
	if not settings.admin_role_profile_fallback and frappe.db.exists(
		"Role Profile", TENANT_ADMIN_PROFILE
	):
		settings.admin_role_profile_fallback = TENANT_ADMIN_PROFILE
		changed = True
	if not settings.notify_on_failure_role and frappe.db.exists(
		"Role", "Platform Tenant Manager"
	):
		settings.notify_on_failure_role = "Platform Tenant Manager"
		changed = True
	if not cint(settings.company_abbr_length):
		settings.company_abbr_length = 4
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
	return changed
