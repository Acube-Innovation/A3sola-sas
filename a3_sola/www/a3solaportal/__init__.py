# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Shared chrome for the signed-in portal.

Every portal page renders the same shell - top bar, left navigation, user footer - and
differs only in its main content. That shell lives in `templates/portal_shell.html`;
this module gives each page's `get_context` one call that fills it, so the navigation and
the identity are defined once rather than copied into each page and drifting apart.
"""

import frappe

# The left-hand navigation, single-sourced here. Two groups mapping onto the app's own
# modules. Routes that have a bespoke portal view point at it; the rest fall back to the
# ERPNext desk list, which exists today, so every link resolves rather than 404ing.
NAV_GROUPS = [
	{
		"label": "Customer Relations",
		"items": [
			{"title": "Leads", "sub": "Prospects and enquiries", "ic": "lead", "route": "/a3solaportal/leads"},
			{"title": "Consumers", "sub": "Homes and businesses", "ic": "user", "route": "/a3solaportal/consumers"},
			{"title": "Proposals", "sub": "Quotes and estimates", "ic": "doc", "route": "/a3solaportal/proposals"},
			{"title": "Cost Estimates", "sub": "Priced quotations", "ic": "calc", "route": "/a3solaportal/cost-estimates"},
			{"title": "Design Estimates", "sub": "System sizing", "ic": "pen", "route": "/a3solaportal/design-estimates"},
			{"title": "Site Surveys", "sub": "Roof and load", "ic": "pin", "route": "/a3solaportal/site-surveys"},
			{"title": "Subsidy Eligibility", "sub": "PM Surya Ghar", "ic": "check", "route": "/a3solaportal/subsidy-eligibility"},
		],
	},
	{
		"label": "Operations Management",
		"items": [
			{"title": "Installations", "sub": "On-site delivery", "ic": "wrench", "route": "/a3solaportal/installations"},
			{"title": "Work Orders", "sub": "Crew scheduling", "ic": "clipboard", "route": "/a3solaportal/work-orders"},
			{"title": "Commissioning", "sub": "Handover reports", "ic": "bolt", "route": "/a3solaportal/commissioning"},
			{"title": "Net Metering", "sub": "DISCOM agreements", "ic": "power", "route": "/a3solaportal/net-metering"},
			{"title": "Subsidy Claims", "sub": "Disbursement tracking", "ic": "wallet", "route": "/a3solaportal/subsidy-claims"},
		],
	},
]

# The top bar names the signed-in user's company: their default Company, else the site's
# default. Shown with the company's logo when one is set on the Company record. The
# product name stays as a fallback for a site with no company yet.
WORKSPACE_NAME = "A3 Sola"


def user_company():
	"""(name, logo_url) for the signed-in user's company, or (fallback, None)."""
	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	if not company or not frappe.db.exists("Company", company):
		return WORKSPACE_NAME, None
	name, logo = frappe.db.get_value("Company", company, ["company_name", "company_logo"]) or (None, None)
	return name or company, logo or None


def require_login(landing):
	"""Send a guest to the portal sign-in and bring them back to `landing` after.

	A redirect rather than a throw, so the visitor lands on a page they can act on. Call
	at the very top of a portal page's `get_context`, before any data is read.
	"""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/a3solaportal/login?redirect-to={landing}"
		raise frappe.Redirect(302)


def fill_shell(context, *, active_route, page_title, crumbs):
	"""Populate the shared shell: identity, navigation, breadcrumbs, page title.

	`active_route` is matched against each nav item's route to mark the current one.
	`crumbs` is a list of {"label", "href"?}; the last entry is rendered as the current
	page. The caller has already run `require_login`, so the session user is real.
	"""
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = page_title

	full_name, email = frappe.db.get_value(
		"User", frappe.session.user, ["full_name", "email"]
	) or (None, None)
	context.user_full_name = full_name or "there"
	context.user_email = email or frappe.session.user
	context.user_first_name = (full_name or "").split(" ")[0] or context.user_full_name

	context.workspace_name, context.workspace_logo = user_company()
	context.nav_groups = NAV_GROUPS
	context.active_route = active_route
	context.page_title = page_title
	context.crumbs = crumbs
	return context
