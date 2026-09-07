# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal dashboard - where a signed-in user lands after login.

Login required. The chrome (top bar, navigation, footer) comes from the shared shell in
`__init__.fill_shell`; this page owns only the summary and action cards. The figures are
representative placeholders a later phase replaces with live counts. The one thing that
is already real is the person - the greeting comes from the session, never the page.
"""

import frappe

from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/dashboard")
	fill_shell(
		context,
		active_route="/a3solaportal/dashboard",
		page_title="Dashboard",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Dashboard"}],
	)
	context.stats = STAT_CARDS
	context.action_cards = ACTION_CARDS
	return context


# --- dashboard content (placeholder figures) ----------------------------------
STAT_CARDS = [
	{"label": "Active Consumers", "value": "128", "note": "across 3 DISCOMs", "ic": "user", "tone": "sky"},
	{"label": "Open Proposals", "value": "17", "note": "₹42.6L pipeline", "ic": "doc", "tone": "amber"},
	{"label": "Installs In Progress", "value": "9", "note": "4 awaiting net meter", "ic": "wrench", "tone": "green"},
]

ACTION_CARDS = [
	{
		"title": "New Lead",
		"text": "Capture an enquiry - name, contact and status - straight into the CRM.",
		"ic": "lead",
		"tone": "amber",
		"cta": "Add a lead",
		"route": "/a3solaportal/leads/new",
	},
	{
		"title": "Installations",
		"text": "Track every job from work order to commissioning, with the DISCOM and bank documents on one record.",
		"ic": "wrench",
		"tone": "sky",
		"cta": "Open installations",
		"route": "/app/solar-installation",
	},
	{
		"title": "Subsidy Pipeline",
		"text": "Follow each PM Surya Ghar claim to the customer's bank account and flag the ones that stall.",
		"ic": "wallet",
		"tone": "green",
		"cta": "View claims",
		"route": "/app/subsidy-claim",
	},
]
