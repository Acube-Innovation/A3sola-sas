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
	# The portal's per-lead pages. `<name>` is one path segment, and Werkzeug prefers a
	# static rule over a dynamic one, so `/leads/new` is listed explicitly or the create
	# page would be read as a lead called "new".
	{"from_route": "/a3solaportal/leads/new", "to_route": "a3solaportal/leads/new"},
	{"from_route": "/a3solaportal/leads/<name>", "to_route": "a3solaportal/leads/view"},
	{"from_route": "/a3solaportal/leads/<name>/edit", "to_route": "a3solaportal/leads/edit"},
	# Collections with a portal detail page (collections.DETAIL_SLUGS), same shape, in the
	# order of the Customer Relations menu and of the chain that walks it.
	{"from_route": "/a3solaportal/consumers/new", "to_route": "a3solaportal/consumers/new"},
	{"from_route": "/a3solaportal/consumers/<name>", "to_route": "a3solaportal/consumers/view"},
	{"from_route": "/a3solaportal/consumers/<name>/edit", "to_route": "a3solaportal/consumers/edit"},
	{"from_route": "/a3solaportal/site-surveys/new", "to_route": "a3solaportal/site-surveys/new"},
	{"from_route": "/a3solaportal/site-surveys/<name>", "to_route": "a3solaportal/site-surveys/view"},
	{"from_route": "/a3solaportal/site-surveys/<name>/edit", "to_route": "a3solaportal/site-surveys/edit"},
	{"from_route": "/a3solaportal/design-estimates/new", "to_route": "a3solaportal/design-estimates/new"},
	{"from_route": "/a3solaportal/design-estimates/<name>", "to_route": "a3solaportal/design-estimates/view"},
	{"from_route": "/a3solaportal/design-estimates/<name>/edit", "to_route": "a3solaportal/design-estimates/edit"},
	{"from_route": "/a3solaportal/subsidy-eligibility/new", "to_route": "a3solaportal/subsidy-eligibility/new"},
	{"from_route": "/a3solaportal/subsidy-eligibility/<name>", "to_route": "a3solaportal/subsidy-eligibility/view"},
	{"from_route": "/a3solaportal/subsidy-eligibility/<name>/edit", "to_route": "a3solaportal/subsidy-eligibility/edit"},
	{"from_route": "/a3solaportal/proposals/new", "to_route": "a3solaportal/proposals/new"},
	{"from_route": "/a3solaportal/proposals/<name>", "to_route": "a3solaportal/proposals/view"},
	{"from_route": "/a3solaportal/proposals/<name>/edit", "to_route": "a3solaportal/proposals/edit"},
	# Quotations open in the pricing builder, which edits a draft in place; there is no
	# separate edit page for them.
	{"from_route": "/a3solaportal/quotations/new", "to_route": "a3solaportal/quotations/new"},
	{"from_route": "/a3solaportal/quotations/<name>", "to_route": "a3solaportal/quotations/view"},
	{"from_route": "/a3solaportal/sales-orders/new", "to_route": "a3solaportal/sales-orders/new"},
	{"from_route": "/a3solaportal/sales-orders/<name>", "to_route": "a3solaportal/sales-orders/view"},
	{"from_route": "/a3solaportal/sales-orders/<name>/edit", "to_route": "a3solaportal/sales-orders/edit"},
	# Solar Operations and Solar Projects. Same shape, one block per collection, in
	# the order of their menus.
	{"from_route": "/a3solaportal/installations/new", "to_route": "a3solaportal/installations/new"},
	{"from_route": "/a3solaportal/installations/<name>", "to_route": "a3solaportal/installations/view"},
	{"from_route": "/a3solaportal/installations/<name>/edit", "to_route": "a3solaportal/installations/edit"},
	{"from_route": "/a3solaportal/installation-tasks/new", "to_route": "a3solaportal/installation-tasks/new"},
	{"from_route": "/a3solaportal/installation-tasks/<name>", "to_route": "a3solaportal/installation-tasks/view"},
	{"from_route": "/a3solaportal/installation-tasks/<name>/edit", "to_route": "a3solaportal/installation-tasks/edit"},
	{"from_route": "/a3solaportal/fee-payments/new", "to_route": "a3solaportal/fee-payments/new"},
	{"from_route": "/a3solaportal/fee-payments/<name>", "to_route": "a3solaportal/fee-payments/view"},
	{"from_route": "/a3solaportal/fee-payments/<name>/edit", "to_route": "a3solaportal/fee-payments/edit"},
	{"from_route": "/a3solaportal/portal-applications/new", "to_route": "a3solaportal/portal-applications/new"},
	{"from_route": "/a3solaportal/portal-applications/<name>", "to_route": "a3solaportal/portal-applications/view"},
	{"from_route": "/a3solaportal/portal-applications/<name>/edit", "to_route": "a3solaportal/portal-applications/edit"},
	{"from_route": "/a3solaportal/loan-applications/new", "to_route": "a3solaportal/loan-applications/new"},
	{"from_route": "/a3solaportal/loan-applications/<name>", "to_route": "a3solaportal/loan-applications/view"},
	{"from_route": "/a3solaportal/loan-applications/<name>/edit", "to_route": "a3solaportal/loan-applications/edit"},
	{"from_route": "/a3solaportal/agreements/new", "to_route": "a3solaportal/agreements/new"},
	{"from_route": "/a3solaportal/agreements/<name>", "to_route": "a3solaportal/agreements/view"},
	{"from_route": "/a3solaportal/agreements/<name>/edit", "to_route": "a3solaportal/agreements/edit"},
	{"from_route": "/a3solaportal/work-orders/new", "to_route": "a3solaportal/work-orders/new"},
	{"from_route": "/a3solaportal/work-orders/<name>", "to_route": "a3solaportal/work-orders/view"},
	{"from_route": "/a3solaportal/work-orders/<name>/edit", "to_route": "a3solaportal/work-orders/edit"},
	{"from_route": "/a3solaportal/purchase-orders/new", "to_route": "a3solaportal/purchase-orders/new"},
	{"from_route": "/a3solaportal/purchase-orders/<name>", "to_route": "a3solaportal/purchase-orders/view"},
	{"from_route": "/a3solaportal/purchase-orders/<name>/edit", "to_route": "a3solaportal/purchase-orders/edit"},
	{"from_route": "/a3solaportal/delivery-notes/new", "to_route": "a3solaportal/delivery-notes/new"},
	{"from_route": "/a3solaportal/delivery-notes/<name>", "to_route": "a3solaportal/delivery-notes/view"},
	{"from_route": "/a3solaportal/delivery-notes/<name>/edit", "to_route": "a3solaportal/delivery-notes/edit"},
	{"from_route": "/a3solaportal/dispatch-notices/new", "to_route": "a3solaportal/dispatch-notices/new"},
	{"from_route": "/a3solaportal/dispatch-notices/<name>", "to_route": "a3solaportal/dispatch-notices/view"},
	{"from_route": "/a3solaportal/dispatch-notices/<name>/edit", "to_route": "a3solaportal/dispatch-notices/edit"},
	{"from_route": "/a3solaportal/document-packs/new", "to_route": "a3solaportal/document-packs/new"},
	{"from_route": "/a3solaportal/document-packs/<name>", "to_route": "a3solaportal/document-packs/view"},
	{"from_route": "/a3solaportal/document-packs/<name>/edit", "to_route": "a3solaportal/document-packs/edit"},
	{"from_route": "/a3solaportal/commissioning/new", "to_route": "a3solaportal/commissioning/new"},
	{"from_route": "/a3solaportal/commissioning/<name>", "to_route": "a3solaportal/commissioning/view"},
	{"from_route": "/a3solaportal/commissioning/<name>/edit", "to_route": "a3solaportal/commissioning/edit"},
	{"from_route": "/a3solaportal/customer-reviews/new", "to_route": "a3solaportal/customer-reviews/new"},
	{"from_route": "/a3solaportal/customer-reviews/<name>", "to_route": "a3solaportal/customer-reviews/view"},
	{"from_route": "/a3solaportal/customer-reviews/<name>/edit", "to_route": "a3solaportal/customer-reviews/edit"},
	{"from_route": "/a3solaportal/subsidy-claims/new", "to_route": "a3solaportal/subsidy-claims/new"},
	{"from_route": "/a3solaportal/subsidy-claims/<name>", "to_route": "a3solaportal/subsidy-claims/view"},
	{"from_route": "/a3solaportal/subsidy-claims/<name>/edit", "to_route": "a3solaportal/subsidy-claims/edit"},
	{"from_route": "/a3solaportal/projects/new", "to_route": "a3solaportal/projects/new"},
	{"from_route": "/a3solaportal/projects/<name>", "to_route": "a3solaportal/projects/view"},
	{"from_route": "/a3solaportal/projects/<name>/edit", "to_route": "a3solaportal/projects/edit"},
	{"from_route": "/a3solaportal/billing-plans/new", "to_route": "a3solaportal/billing-plans/new"},
	{"from_route": "/a3solaportal/billing-plans/<name>", "to_route": "a3solaportal/billing-plans/view"},
	{"from_route": "/a3solaportal/billing-plans/<name>/edit", "to_route": "a3solaportal/billing-plans/edit"},
	{"from_route": "/a3solaportal/sales-invoices/new", "to_route": "a3solaportal/sales-invoices/new"},
	{"from_route": "/a3solaportal/sales-invoices/<name>", "to_route": "a3solaportal/sales-invoices/view"},
	{"from_route": "/a3solaportal/sales-invoices/<name>/edit", "to_route": "a3solaportal/sales-invoices/edit"},
	{"from_route": "/a3solaportal/payment-entries/new", "to_route": "a3solaportal/payment-entries/new"},
	{"from_route": "/a3solaportal/payment-entries/<name>", "to_route": "a3solaportal/payment-entries/view"},
	{"from_route": "/a3solaportal/payment-entries/<name>/edit", "to_route": "a3solaportal/payment-entries/edit"},
	{"from_route": "/a3solaportal/om-contracts/new", "to_route": "a3solaportal/om-contracts/new"},
	{"from_route": "/a3solaportal/om-contracts/<name>", "to_route": "a3solaportal/om-contracts/view"},
	{"from_route": "/a3solaportal/om-contracts/<name>/edit", "to_route": "a3solaportal/om-contracts/edit"},
	{"from_route": "/a3solaportal/om-visits/new", "to_route": "a3solaportal/om-visits/new"},
	{"from_route": "/a3solaportal/om-visits/<name>", "to_route": "a3solaportal/om-visits/view"},
	{"from_route": "/a3solaportal/om-visits/<name>/edit", "to_route": "a3solaportal/om-visits/edit"},
	{"from_route": "/a3solaportal/service-tickets/new", "to_route": "a3solaportal/service-tickets/new"},
	{"from_route": "/a3solaportal/service-tickets/<name>", "to_route": "a3solaportal/service-tickets/view"},
	{"from_route": "/a3solaportal/service-tickets/<name>/edit", "to_route": "a3solaportal/service-tickets/edit"},
	{"from_route": "/a3solaportal/warranty-claims/new", "to_route": "a3solaportal/warranty-claims/new"},
	{"from_route": "/a3solaportal/warranty-claims/<name>", "to_route": "a3solaportal/warranty-claims/view"},
	{"from_route": "/a3solaportal/warranty-claims/<name>/edit", "to_route": "a3solaportal/warranty-claims/edit"},
	{"from_route": "/a3solaportal/generation-readings/new", "to_route": "a3solaportal/generation-readings/new"},
	{"from_route": "/a3solaportal/generation-readings/<name>", "to_route": "a3solaportal/generation-readings/view"},
	{"from_route": "/a3solaportal/generation-readings/<name>/edit", "to_route": "a3solaportal/generation-readings/edit"},
	{"from_route": "/a3solaportal/fee-recoveries/new", "to_route": "a3solaportal/fee-recoveries/new"},
	{"from_route": "/a3solaportal/fee-recoveries/<name>", "to_route": "a3solaportal/fee-recoveries/view"},
	{"from_route": "/a3solaportal/fee-recoveries/<name>/edit", "to_route": "a3solaportal/fee-recoveries/edit"},
	{"from_route": "/a3solaportal/installation-snags/new", "to_route": "a3solaportal/installation-snags/new"},
	{"from_route": "/a3solaportal/installation-snags/<name>", "to_route": "a3solaportal/installation-snags/view"},
	{"from_route": "/a3solaportal/installation-snags/<name>/edit", "to_route": "a3solaportal/installation-snags/edit"},
	{"from_route": "/a3solaportal/material-requests/new", "to_route": "a3solaportal/material-requests/new"},
	{"from_route": "/a3solaportal/material-requests/<name>", "to_route": "a3solaportal/material-requests/view"},
	{"from_route": "/a3solaportal/material-requests/<name>/edit", "to_route": "a3solaportal/material-requests/edit"},
	{"from_route": "/a3solaportal/purchase-receipts/new", "to_route": "a3solaportal/purchase-receipts/new"},
	{"from_route": "/a3solaportal/purchase-receipts/<name>", "to_route": "a3solaportal/purchase-receipts/view"},
	{"from_route": "/a3solaportal/purchase-receipts/<name>/edit", "to_route": "a3solaportal/purchase-receipts/edit"},
	{"from_route": "/a3solaportal/stock-entries/new", "to_route": "a3solaportal/stock-entries/new"},
	{"from_route": "/a3solaportal/stock-entries/<name>", "to_route": "a3solaportal/stock-entries/view"},
	{"from_route": "/a3solaportal/stock-entries/<name>/edit", "to_route": "a3solaportal/stock-entries/edit"},
	{"from_route": "/a3solaportal/serial-numbers/new", "to_route": "a3solaportal/serial-numbers/new"},
	{"from_route": "/a3solaportal/serial-numbers/<name>", "to_route": "a3solaportal/serial-numbers/view"},
	{"from_route": "/a3solaportal/serial-numbers/<name>/edit", "to_route": "a3solaportal/serial-numbers/edit"},
	{"from_route": "/a3solaportal/journal-entries/new", "to_route": "a3solaportal/journal-entries/new"},
	{"from_route": "/a3solaportal/journal-entries/<name>", "to_route": "a3solaportal/journal-entries/view"},
	{"from_route": "/a3solaportal/journal-entries/<name>/edit", "to_route": "a3solaportal/journal-entries/edit"},
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
