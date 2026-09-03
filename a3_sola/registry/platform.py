# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Registry for the Platform module.

A NOTE THAT MATTERS, so a later phase does not "fix" it:

Phase 4 doctypes are PLATFORM-level, not tenant-level. A Platform Feature belongs to the
product, not to a customer, and a Subscription Signup is created before any tenant exists.
They therefore carry NO company field and are NOT registered for company isolation - that
would be meaningless here and would break the public site.

They are isolated a different way, which is the one that matters for them: the guest role
gets read access to published marketing content and to nothing else, and there is a test
that enumerates every doctype in the whole app to prove it.
"""

MODULE_NAME = "Platform"

#: Content the public site renders. Guest may read these when published.
PUBLIC_CONTENT_DOCTYPES = [
	"Platform Feature",
	"Platform Solution",
	"Platform Integration",
	"Platform Stat",
	"Platform FAQ",
	"Subscription Plan",
	"Platform Legal Page",
	"Platform Bullet",
	"Platform Detail Section",
	"Plan Feature",
	"Plan Module",
]

#: The funnel. These hold personal data and are NOT public - see the permission allowlist
#: test, which enumerates every doctype in the app and proves guest cannot reach them.
#: Payments. Guest has NO permission on any of these - a Payment Order readable by a
#: logged-out visitor would be a serious breach, and the allowlist test proves it is not.
PAYMENT_DOCTYPES = [
	"Payment Order",
	"Payment Transaction",
	"Payment Webhook Log",
	"Payment Mandate",
	"Platform Subscription",
	"Subscription Billing Cycle",
	"Subscription Invoice",
	"Subscription Invoice Item",
	"Payment Refund",
	"Dunning Policy",
	"Dunning Policy Step",
	"Dunning Attempt",
	"Gateway Error Class",
	"Settlement Reconciliation",
	"Settlement Line",
	"Platform Payment Account Mapping",
	"Platform Audit Entry",
]

#: Provisioning. Guest has NO permission on any of these either - a Tenant readable by a
#: logged-out visitor would expose the entire customer list, and a Provisioning Job would
#: expose their administrators' email addresses.
PROVISIONING_DOCTYPES = [
	"Tenant",
	"Tenant Module",
	"Tenant User",
	"Tenant Isolation Test Result",
	"Tenant Onboarding Task",
	"Tenant Blueprint",
	"Blueprint Seed Item",
	"Provisioning Job",
	"Provisioning Step Log",
	"Tenant Invitation",
]

#: Phase 7. Subscription lifecycle and access control. Guest has NO permission on any of
#: these: a Subscription Event readable by a logged-out visitor would publish which
#: customers are behind on payment, and an Access Suspension would publish their staff.
LIFECYCLE_DOCTYPES = [
	"Subscription Policy",
	"Policy Stage",
	"Subscription Event",
	"Access Suspension",
	"Suspended User Snapshot",
	"Plan Change Request",
	"Proration Line",
	"Seat Change Request",
	"Cancellation Request",
]

FUNNEL_DOCTYPES = [
	"Subscription Signup",
	"Demo Request",
	"Signup Event Log",
]

DOCTYPES = (
	PUBLIC_CONTENT_DOCTYPES
	+ FUNNEL_DOCTYPES
	+ PAYMENT_DOCTYPES
	+ PROVISIONING_DOCTYPES
	+ LIFECYCLE_DOCTYPES
)

#: Deliberately empty. See the module docstring: these records are not tenant-scoped, so
#: binding them to the company permission hooks would filter public content to nothing.
PERMISSION_DOCTYPES = []

#: Seat enforcement lives on the User document itself, because that is the only place
#: where "one more user" is an event rather than a report. See api/entitlements.py.
DOC_EVENTS = {
	# Registered on the wildcard so a doctype added by a later phase cannot quietly slip
	# past the Read Only access effect. It refuses submit, cancel and amend only - reading,
	# reporting and printing stay open, because a restricted tenant must still be able to
	# retrieve their own data.
	"*": {
		"on_submit": ["a3_sola.api.lifecycle.gate.block_writes"],
		"on_cancel": ["a3_sola.api.lifecycle.gate.block_writes"],
		"on_update_after_submit": ["a3_sola.api.lifecycle.gate.block_writes"],
	},
	"User": {
		"validate": ["a3_sola.api.entitlements.before_user_save"],
		"on_update": ["a3_sola.api.entitlements.after_user_change"],
		"after_insert": ["a3_sola.api.entitlements.after_user_change"],
	},
}

SCHEDULER_EVENTS = {
	"hourly": [
		"a3_sola.api.reconciliation.gateway_health_check",
		# The watchdog runs hourly so a stopped daily job is noticed the same day rather
		# than the next. It stamps its own heartbeat, so a watchdog that dies is itself
		# detectable - one level up, by the external check on the health endpoint.
		"a3_sola.api.monitoring.heartbeat.watchdog",
	],
	"daily": [
		# Recurring collection. Every pass is idempotent and safe to re-run.
		"a3_sola.api.billing_engine.run_daily_billing",
		"a3_sola.api.webhooks.retry_failed_webhooks",
		"a3_sola.api.dunning.run_dunning",
		"a3_sola.platform.doctype.payment_refund.payment_refund.detect_duplicate_payments",
		"a3_sola.api.reconciliation.alert_on_unreconciled",
		"a3_sola.platform.doctype.platform_audit_entry.platform_audit_entry.alert_on_broken_audit_chain",
		"a3_sola.api.funnel_jobs.chase_and_abandon_signups",
		# Data minimisation, on by default. See docs/SECURITY_NOTES.md.
		"a3_sola.api.funnel_jobs.purge_personal_data",
		# Provisioning.
		"a3_sola.api.provisioning.orchestrator.watchdog",
		"a3_sola.api.provisioning.orchestrator.alert_on_open_interventions",
		"a3_sola.api.entitlements.recalculate_all_usage",
		"a3_sola.api.invitations.expire_stale_invitations",
		# Lifecycle. Ships inert - dry run on, automatic suspension off - so these
		# evaluate every subscription, write down every decision, and change nothing.
		"a3_sola.api.lifecycle.engine.run_lifecycle",
		"a3_sola.api.lifecycle.engine.alert_on_missing_heartbeat",
		"a3_sola.api.lifecycle.suspension.remind_pending",
		# Business anomalies, routed by severity. See docs/ops/MONITORING.md for each
		# check's expected frequency at 50 tenants.
		"a3_sola.api.monitoring.alerts.run_business_alerts",
		# Error Log has no retention by default and reached 165 MB on this bench.
		"a3_sola.api.monitoring.jobs.purge_error_log",
	],
	"monthly": [
		"a3_sola.api.accounting_payments.release_deferred_revenue",
		# A regression introduced by a later phase should be found by us, not by a customer.
		"a3_sola.api.isolation.monthly_isolation_sweep",
		# Phase 8's adversarial suite, read-only, against live data. The Phase 6 sweep
		# above checks that a tenant is isolated; this one actively attacks it.
		"a3_sola.api.security.audit.monthly_isolation_audit",
	],
	"weekly": ["a3_sola.api.funnel_jobs.weekly_funnel_summary"],
}

#: The funnel's sub-pages sit under /get-started/, but Frappe cannot import a controller
#: from a hyphenated directory - so the templates live at the top level and are routed
#: here to the URLs the pricing CTAs and the emails actually point at.
#: Only the URLs that cannot resolve from a file path on their own. Everything else under
#: `www/a3sola/` is served by Frappe from its location, which is why the pages were moved
#: there rather than left at the root behind a rule - a rule cannot stop Frappe serving
#: `www/index.html` at `/`, and `/` belongs to the desk.
WEBSITE_ROUTE_RULES = [
	# The funnel's sub-pages read as one path to a visitor and live as two flat files,
	# because Frappe cannot import a controller from a hyphenated directory.
	{"from_route": "/a3sola/get-started/summary", "to_route": "a3sola/signup-summary"},
	{"from_route": "/a3sola/get-started/check-email", "to_route": "a3sola/signup-check-email"},
	# Portal pages stay at the root: they are logged-in app surfaces reached from Frappe's
	# portal menu, not part of the public site.
	{"from_route": "/account-mapping", "to_route": "account_mapping"},
]

#: Attached to every website request so a page added later cannot skip the chrome - or,
#: more importantly, skip the maintenance-mode check.
WEBSITE_CONTEXT = ["a3_sola.api.platform.update_website_context"]

#: The subscribed customer's own billing page.
PORTAL_MENU_ITEMS = [
	{"title": "Billing", "route": "/billing", "reference_doctype": "", "role": "Customer"},
	{"title": "Team & Seats", "route": "/seats", "reference_doctype": "", "role": "Customer"},
	{"title": "Setup", "route": "/onboarding", "reference_doctype": "", "role": "Customer"},
]

FIXTURES = [
	{"dt": "Custom Field", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Property Setter", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Notification", "filters": [["module", "=", MODULE_NAME]]},
]
