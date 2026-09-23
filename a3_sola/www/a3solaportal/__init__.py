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
#
# Each group carries a `key`: a stable id the shell uses for the heading's `aria-controls`
# and for remembering, per browser, whether the group is open. It is spelled out rather
# than derived from the label so that renaming a head never silently resets the state.
NAV_GROUPS = [
	{
		"key": "customer-relations",
		"label": "Customer Relations",
		# In the order the work happens: each item is the step after the one above it, and
		# the chain in `a3_sola.api.portal_chain` creates them in exactly this sequence.
		"items": [
			{"title": "Lead", "sub": "Prospects and enquiries", "ic": "lead", "route": "/a3solaportal/leads"},
			{"title": "Solar Consumer", "sub": "Homes and businesses", "ic": "user", "route": "/a3solaportal/consumers"},
			{"title": "Site Survey", "sub": "Roof and load", "ic": "pin", "route": "/a3solaportal/site-surveys"},
			{"title": "Solar Design Estimate", "sub": "System sizing", "ic": "pen", "route": "/a3solaportal/design-estimates"},
			{"title": "Subsidy Eligibility Check", "sub": "PM Surya Ghar", "ic": "check", "route": "/a3solaportal/subsidy-eligibility"},
			{"title": "Solar Proposal", "sub": "Offer document", "ic": "doc", "route": "/a3solaportal/proposals"},
			{"title": "Quotation", "sub": "Priced offer", "ic": "calc", "route": "/a3solaportal/quotations"},
			{"title": "Sales Order", "sub": "Confirmed orders", "ic": "cart", "route": "/a3solaportal/sales-orders"},
		],
	},
	{
		"key": "operations-management",
		"label": "Operations Management",
		# The thirty tasks of a job, grouped as the work happens: paperwork, then
		# materials, then the site, then commissioning, then closing. Each item is the
		# document a task is executed in.
		"items": [
			{"title": "Solar Installation", "sub": "The job itself", "ic": "wrench", "route": "/a3solaportal/installations"},
			{"title": "Installation Task", "sub": "The thirty tasks", "ic": "checklist", "route": "/a3solaportal/installation-tasks"},
			{"title": "Statutory Fee Payment", "sub": "Form 1, Form 2, meter", "ic": "cash", "route": "/a3solaportal/fee-payments"},
			{"title": "Portal Application", "sub": "PM Surya Ghar, CEIG", "ic": "globe", "route": "/a3solaportal/portal-applications"},
			{"title": "Loan Application", "sub": "Financed jobs", "ic": "bank", "route": "/a3solaportal/loan-applications"},
			{"title": "Solar Agreement", "sub": "Stamp paper and terms", "ic": "scroll", "route": "/a3solaportal/agreements"},
			{"title": "Installation Work Order", "sub": "Structure and install", "ic": "clipboard", "route": "/a3solaportal/work-orders"},
			{"title": "Purchase Order", "sub": "Material procurement", "ic": "box", "route": "/a3solaportal/purchase-orders"},
			{"title": "Delivery Note", "sub": "Material dispatch", "ic": "truck", "route": "/a3solaportal/delivery-notes"},
			{"title": "Material Dispatch Notice", "sub": "Serials to contractor", "ic": "package", "route": "/a3solaportal/dispatch-notices"},
			{"title": "Document Pack", "sub": "Form 2 and 3, handover", "ic": "stack", "route": "/a3solaportal/document-packs"},
			{"title": "Commissioning Report", "sub": "Handover reports", "ic": "bolt", "route": "/a3solaportal/commissioning"},
			{"title": "Installation Snag", "sub": "Defects and rectification", "ic": "alert", "route": "/a3solaportal/installation-snags"},
			{"title": "Customer Review", "sub": "Feedback and Google", "ic": "star", "route": "/a3solaportal/customer-reviews"},
			{"title": "Subsidy Claim", "sub": "Request to disbursement", "ic": "wallet", "route": "/a3solaportal/subsidy-claims"},
		],
	},
	{
		"key": "project-management",
		"label": "Project Management",
		# What happens after commissioning: the project opens, it is billed, and it is
		# serviced for the life of the guarantee.
		"items": [
			{"title": "Project", "sub": "Delivery and service", "ic": "briefcase", "route": "/a3solaportal/projects"},
			{"title": "Solar Billing Plan", "sub": "Milestones to invoice", "ic": "calendar", "route": "/a3solaportal/billing-plans"},
			{"title": "Sales Invoice", "sub": "Raised against milestones", "ic": "receipt", "route": "/a3solaportal/sales-invoices"},
			{"title": "Payment Entry", "sub": "Money received", "ic": "wallet", "route": "/a3solaportal/payment-entries"},
			{"title": "Solar OM Contract", "sub": "Service cover", "ic": "scroll", "route": "/a3solaportal/om-contracts"},
			{"title": "Solar OM Visit", "sub": "Scheduled maintenance", "ic": "pin", "route": "/a3solaportal/om-visits"},
			{"title": "Service Ticket", "sub": "Faults and requests", "ic": "ticket", "route": "/a3solaportal/service-tickets"},
			{"title": "Solar Warranty Claim", "sub": "Against the supplier", "ic": "shield", "route": "/a3solaportal/warranty-claims"},
			{"title": "Generation Reading", "sub": "Output vs guarantee", "ic": "gauge", "route": "/a3solaportal/generation-readings"},
			{"title": "Statutory Fee Recovery", "sub": "Fees fronted, recovered", "ic": "refund", "route": "/a3solaportal/fee-recoveries"},
		],
	},
	{
		"key": "stores-accounts",
		"label": "Stores & Accounts",
		# Standard ERPNext documents, listed here because the operations team lives in
		# them daily and the app extends each one with the job it belongs to.
		"items": [
			{"title": "Material Request", "sub": "Procurement raised", "ic": "request", "route": "/a3solaportal/material-requests"},
			{"title": "Purchase Receipt", "sub": "Goods received", "ic": "inbox", "route": "/a3solaportal/purchase-receipts"},
			{"title": "Stock Entry", "sub": "Issued to site", "ic": "transfer", "route": "/a3solaportal/stock-entries"},
			{"title": "Serial No", "sub": "Modules and inverters", "ic": "barcode", "route": "/a3solaportal/serial-numbers"},
			{"title": "Journal Entry", "sub": "Accounting adjustments", "ic": "ledger", "route": "/a3solaportal/journal-entries"},
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
