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
FUNNEL_DOCTYPES = [
	"Subscription Signup",
	"Demo Request",
	"Signup Event Log",
]

DOCTYPES = PUBLIC_CONTENT_DOCTYPES + FUNNEL_DOCTYPES

#: Deliberately empty. See the module docstring: these records are not tenant-scoped, so
#: binding them to the company permission hooks would filter public content to nothing.
PERMISSION_DOCTYPES = []

DOC_EVENTS = {}

SCHEDULER_EVENTS = {
	"daily": [
		"a3_sola.api.funnel_jobs.chase_and_abandon_signups",
		# Data minimisation, on by default. See docs/SECURITY_NOTES.md.
		"a3_sola.api.funnel_jobs.purge_personal_data",
	],
	"weekly": ["a3_sola.api.funnel_jobs.weekly_funnel_summary"],
}

#: The funnel's sub-pages sit under /get-started/, but Frappe cannot import a controller
#: from a hyphenated directory - so the templates live at the top level and are routed
#: here to the URLs the pricing CTAs and the emails actually point at.
WEBSITE_ROUTE_RULES = [
	{"from_route": "/get-started/summary", "to_route": "signup-summary"},
	{"from_route": "/get-started/check-email", "to_route": "signup-check-email"},
]

#: Attached to every website request so a page added later cannot skip the chrome - or,
#: more importantly, skip the maintenance-mode check.
WEBSITE_CONTEXT = ["a3_sola.api.platform.update_website_context"]

FIXTURES = [
	{"dt": "Custom Field", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Property Setter", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Notification", "filters": [["module", "=", MODULE_NAME]]},
]
