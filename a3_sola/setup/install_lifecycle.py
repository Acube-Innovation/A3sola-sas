# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Phase 7 setup: the three lifecycle roles, and the policy every tenant starts under.

The policy seeded here is the recommended starting point, not a default the client is
stuck with. Every number in it is a row they can edit - see docs/POLICY_GUIDE.md for what
each one costs you when it is too lax and what it costs you when it is too aggressive.
"""

import frappe
from frappe.utils import cint

MODULE = "Platform"

LIFECYCLE_ROLES = [
	(
		"Platform Lifecycle Operator",
		"Watches the lifecycle engine. Can extend grace and restore access. "
		"Cannot suspend and cannot cancel.",
	),
	(
		"Platform Retention Manager",
		"Cancellations, retention offers and plan changes. Cannot suspend.",
	),
	(
		"Platform Admin",
		"Policies, lifecycle settings, bulk operations and suspension approval.",
	),
]

LIFECYCLE_ROLE_PROFILES = {
	"Platform Lifecycle": ["Platform Lifecycle Operator"],
	"Platform Retention": ["Platform Retention Manager", "Platform Lifecycle Operator"],
}

DEFAULT_POLICY = "Standard Non-Payment Policy"

#: One template per notifying stage, so the recommended policy can actually pass the
#: pre-flight check. Shipping a default policy that fails its own gate would mean every
#: client had to write five emails before they could switch the engine on, and most would
#: instead switch the check off.
#:
#: The copy is deliberately plain and says the same three things every time: what happened,
#: what it costs, and that paying reverses it at once.
STAGE_TEMPLATES = {
	"PASTDUE": (
		"A3 Sola: your payment did not go through",
		"<p>Hello,</p>"
		"<p>We could not collect your A3 Sola subscription this cycle. This is usually the "
		"bank rather than anything you have done - an expired card, or a limit.</p>"
		"<p><b>Nothing has changed about your access.</b> Everyone can carry on working.</p>"
		"<p>Updating your payment method takes a minute: "
		"<a href='{{ pay_url }}'>your billing page</a>.</p>",
	),
	"GRACE": (
		"A3 Sola: action needed on your subscription",
		"<p>Hello,</p>"
		"<p>Your A3 Sola subscription is still unpaid, so everyone in your team will now see "
		"a notice at the top of the screen. It does not stop anyone working.</p>"
		"<p>If this is not settled, access will eventually be paused - you will be warned "
		"before that, with the exact date.</p>"
		"<p><a href='{{ pay_url }}'>Settle it now</a></p>",
	),
	"WARN": (
		"A3 Sola: your access will be paused on {{ suspension_date }}",
		"<p>Hello,</p>"
		"<p>Unless the outstanding amount is settled, access to A3 Sola for your team will "
		"be paused on <b>{{ suspension_date }}</b>.</p>"
		"<p><b>Nothing will be deleted.</b> Your data, your users and their permissions stay "
		"exactly as they are, and access comes back the moment payment clears.</p>"
		"<p><a href='{{ pay_url }}'>Pay now and stop this</a></p>",
	),
	"SUSPEND": (
		"A3 Sola: your access has been paused",
		"<p>Hello,</p>"
		"<p>Access to A3 Sola has been paused because of an unpaid invoice.</p>"
		"<p><b>Nothing has been deleted.</b> Every record, user and permission is exactly as "
		"you left it.</p>"
		"<p>Paying restores access immediately - not after a support ticket, and not the "
		"next morning.</p>"
		"<p><a href='{{ pay_url }}'>Pay and restore access</a></p>",
	),
	"CANCEL": (
		"A3 Sola: your subscription has ended",
		"<p>Hello,</p>"
		"<p>Your A3 Sola subscription has ended.</p>"
		"<p>Your data has been exported for you and is ready to download, and your account "
		"can be reactivated - everything comes back exactly as you left it.</p>"
		"<p><a href='{{ pay_url }}'>Reactivate</a></p>",
	),
}

#: (code, from, to, trigger, day, effect, approval, notify, description)
#:
#: The shape of this is the argument. Nothing restrictive happens for a week, because a
#: failed payment is usually a bank problem. Restriction then starts as a banner, which
#: does not obstruct work. Blocking comes only after a warning, on day 15, and only with a
#: human approving it.
DEFAULT_STAGES = [
	("PASTDUE", "Active", "Past Due", "Days After Due Date", 0, "None", 0, 1,
	 "Payment failed. Access untouched - this is usually the bank, not the customer."),
	("GRACE", "Past Due", "Grace", "Days After Due Date", 7, "Banner Only", 0, 1,
	 "A week unpaid. A persistent banner showing the amount and a pay-now link. Work is "
	 "not obstructed."),
	("WARN", "Grace", "Grace", "Days After Due Date", 12, "Banner Only", 0, 1,
	 "Final warning, naming the exact date and time access will be paused."),
	("SUSPEND", "Grace", "Suspended", "Days After Due Date", 15, "Blocked", 1, 1,
	 "Access paused. Nothing is deleted; a person approves this, and paying reverses it "
	 "in seconds."),
	("CANCEL", "Suspended", "Cancelled", "Days After Due Date", 60, "Blocked", 1, 1,
	 "Two months unpaid. The subscription ends, the data export is generated, and "
	 "reactivation stays open for the configured window."),
]


def setup():
	"""Idempotent. Safe on every migrate."""
	create_roles()
	seed_templates()
	seed_default_policy()
	backfill_policy_templates()
	set_defaults()


def seed_templates():
	"""Create the stage emails once. Never overwrite - the client will edit this copy."""
	created = []
	for code, (subject, body) in STAGE_TEMPLATES.items():
		name = _template_name(code)
		if frappe.db.exists("Email Template", name):
			continue
		doc = frappe.get_doc({
			"doctype": "Email Template", "__newname": name,
			"subject": subject, "use_html": 1, "response_html": body, "response": body,
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		created.append(name)
	return created


def backfill_policy_templates():
	"""Point each stage of the seeded policy at its template, if it has none.

	Written with `db_set` on the row rather than by saving the policy: a client who has
	edited their thresholds must not have them revalidated by a migration, and a stage
	they deliberately pointed elsewhere must be left alone.
	"""
	if not frappe.db.exists("Subscription Policy", DEFAULT_POLICY):
		return []
	filled = []
	for row in frappe.get_all(
		"Policy Stage",
		filters={"parent": DEFAULT_POLICY, "parenttype": "Subscription Policy"},
		fields=["name", "stage_code", "notification_template", "notify_tenant"],
	):
		if row.notification_template or not cint(row.notify_tenant):
			continue
		template = _template_name(row.stage_code)
		if not frappe.db.exists("Email Template", template):
			continue
		frappe.db.set_value("Policy Stage", row.name, "notification_template", template,
		                    update_modified=False)
		filled.append(row.stage_code)
	return filled


def _template_name(stage_code):
	return f"A3 Sola Lifecycle {stage_code.title()}"


def create_roles():
	for role, description in LIFECYCLE_ROLES:
		if frappe.db.exists("Role", role):
			continue
		doc = frappe.get_doc({
			"doctype": "Role", "role_name": role, "desk_access": 1,
			"description": description,
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)

	for profile, roles in LIFECYCLE_ROLE_PROFILES.items():
		roles = [r for r in roles if frappe.db.exists("Role", r)]
		if not roles:
			continue
		if frappe.db.exists("Role Profile", profile):
			doc = frappe.get_doc("Role Profile", profile)
			have = {r.role for r in doc.roles}
			missing = [r for r in roles if r not in have]
			if not missing:
				continue
			for role in missing:
				doc.append("roles", {"role": role})
		else:
			doc = frappe.get_doc({
				"doctype": "Role Profile", "role_profile": profile,
				"roles": [{"role": r} for r in roles],
			})
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)


def seed_default_policy():
	"""Create the starting policy once. Never overwrite it - the client will edit it."""
	if frappe.db.exists("Subscription Policy", DEFAULT_POLICY):
		return DEFAULT_POLICY

	doc = frappe.get_doc({
		"doctype": "Subscription Policy",
		"policy_name": DEFAULT_POLICY,
		"applicable_cycle": "All",
		"is_default": 1,
		"is_active": 1,
		"grace_period_days": 7,
		"suspension_after_days": 15,
		"cancellation_after_days": 60,
		"allow_reactivation": 1,
		"reactivation_requires_full_payment": 1,
		"description": (
			"The recommended starting point. Nothing restrictive happens for a week, "
			"restriction starts as a banner rather than a block, and access is only "
			"paused after a warning and a human approval. Every number here is editable - "
			"see docs/POLICY_GUIDE.md for what moving each one costs."
		),
		"stages": [
			{
				"sequence": index,
				"stage_code": code,
				"from_state": frm,
				"to_state": to,
				"trigger_type": trigger,
				"day_offset": day,
				"access_effect": effect,
				"requires_approval": approval,
				"notify_tenant": notify,
				"is_reversible": 1,
				"description": description,
			}
			for index, (code, frm, to, trigger, day, effect, approval, notify, description)
			in enumerate(DEFAULT_STAGES, start=1)
		],
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def set_defaults():
	"""Point Settings at the seeded policy and the approval role, once.

	Deliberately does not touch `dry_run_mode` or `enable_automatic_suspension`. Those
	ship inert and only a person turns them on.
	"""
	values = {}
	if not frappe.db.get_single_value("A3 Sola Settings", "default_subscription_policy"):
		if frappe.db.exists("Subscription Policy", DEFAULT_POLICY):
			values["default_subscription_policy"] = DEFAULT_POLICY
	if not frappe.db.get_single_value("A3 Sola Settings", "suspension_approval_role"):
		values["suspension_approval_role"] = "Platform Admin"
	if not frappe.db.get_single_value("A3 Sola Settings", "lifecycle_alert_role"):
		values["lifecycle_alert_role"] = "Platform Admin"
	if values:
		frappe.db.set_single_value("A3 Sola Settings", values)
	return values
