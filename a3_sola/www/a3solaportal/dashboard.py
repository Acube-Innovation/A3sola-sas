# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal dashboard - where a signed-in user lands after login.

Login required. The chrome (top bar, navigation, footer) comes from the shared shell in
`__init__.fill_shell`; this page owns the person's work and the action cards. The work is
theirs (api/my_work.py): what is pending - late, or with no date - what is due today and
what is due in the next seven days, each linked to where it is done. A manager may switch
to the whole team's (`?scope=team`).
"""

import frappe

from a3_sola.api import my_work
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
	user = frappe.session.user
	context.can_team = my_work.is_manager(user)
	context.scope = "team" if context.can_team and frappe.form_dict.get("scope") == "team" else "mine"
	work = my_work.items(user, team=context.scope == "team")
	if context.scope == "team":
		my_work.people_names(work)
	context.work = my_work.buckets(work)
	context.work_columns = [
		{"key": "pending", "title": "Pending", "note": "Late, or with no date yet", "tone": "red"},
		{"key": "today", "title": "Today", "note": frappe.utils.formatdate(frappe.utils.today(), "EEEE, d MMM"), "tone": "amber"},
		{"key": "upcoming", "title": "Upcoming", "note": "Next {0} days".format(my_work.UPCOMING_DAYS), "tone": "sky"},
	]
	context.show_per_column = SHOW_PER_COLUMN
	counts = context.work["counts"]
	context.stats = [
		{"label": "Overdue", "value": counts["overdue"], "note": "past their due date", "ic": "alert", "tone": "red"},
		{"label": "Due today", "value": counts["today"], "note": "to finish today", "ic": "calendar", "tone": "amber"},
		{"label": "Next 7 days", "value": counts["upcoming"],
			"note": "{0} more later".format(context.work["later"]) if context.work["later"] else "coming up", "ic": "clipboard", "tone": "sky"},
		{"label": "No date", "value": counts["undated"], "note": "open, not yet dated", "ic": "inbox", "tone": "green"},
	]
	context.action_cards = ACTION_CARDS
	return context


#: Items shown in each column; the rest are counted.
SHOW_PER_COLUMN = 15

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
