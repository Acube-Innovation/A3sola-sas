# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Platform dashboard: what the funnel is doing this month."""

import json

import frappe

MODULE = "Platform"

NUMBER_CARDS = [
	("Signups This Month", "Subscription Signup", "Count", None,
	 [["docstatus", "<", 2]], "Blue"),
	("Verified Signups", "Subscription Signup", "Count", None,
	 [["is_email_verified", "=", 1], ["docstatus", "<", 2]], "Green"),
	("Awaiting Payment", "Subscription Signup", "Count", None,
	 [["status", "in", ["Verified", "Awaiting Payment"]], ["docstatus", "<", 2]], "Orange"),
	("Pipeline Value of Verified Signups", "Subscription Signup", "Sum", "total_amount",
	 [["is_email_verified", "=", 1], ["status", "not in", ["Abandoned", "Rejected"]],
	  ["docstatus", "<", 2]], "Purple"),
	("Abandoned This Month", "Subscription Signup", "Count", None,
	 [["status", "=", "Abandoned"], ["docstatus", "<", 2]], "Red"),
	("Demo Requests This Month", "Demo Request", "Count", None, [], "Blue"),
	("Demo Requests Unassigned", "Demo Request", "Count", None,
	 [["status", "=", "New"], ["assigned_to", "is", "not set"]], "Orange"),
	("Published Features", "Platform Feature", "Count", None, [["is_published", "=", 1]], "Grey"),
]

CHARTS = [
	{
		"name": "Daily Signups",
		"chart_name": "Daily Signups",
		"chart_type": "Count",
		"document_type": "Subscription Signup",
		"based_on": "creation",
		"timespan": "Last Quarter",
		"time_interval": "Daily",
		"type": "Line",
	},
	{
		"name": "Signups by Plan",
		"chart_name": "Signups by Plan",
		"chart_type": "Group By",
		"document_type": "Subscription Signup",
		"group_by_type": "Count",
		"group_by_based_on": "plan_code",
		"type": "Donut",
		"number_of_groups": 5,
	},
	{
		"name": "Signup Funnel Drop-off",
		"chart_name": "Signup Funnel Drop-off",
		"chart_type": "Group By",
		"document_type": "Subscription Signup",
		"group_by_type": "Count",
		"group_by_based_on": "status",
		"type": "Bar",
		"number_of_groups": 10,
	},
	{
		"name": "Acquisition Source Mix",
		"chart_name": "Acquisition Source Mix",
		"chart_type": "Group By",
		"document_type": "Subscription Signup",
		"group_by_type": "Count",
		"group_by_based_on": "utm_source",
		"type": "Donut",
		"number_of_groups": 6,
	},
	{
		"name": "Demo Requests by Status",
		"chart_name": "Demo Requests by Status",
		"chart_type": "Group By",
		"document_type": "Demo Request",
		"group_by_type": "Count",
		"group_by_based_on": "status",
		"type": "Bar",
		"number_of_groups": 7,
	},
]

NOTIFICATIONS = [
	{
		"name": "Platform New Signup",
		"subject": "New signup: {{ doc.organisation_name }}",
		"document_type": "Subscription Signup",
		"event": "New",
		"message": "A new subscription signup has arrived from the public site. It is "
		"awaiting email verification.",
		"recipients_role": "Platform Sales",
	},
	{
		"name": "Platform Signup Verified",
		"subject": "{{ doc.organisation_name }} verified their email",
		"document_type": "Subscription Signup",
		"event": "Value Change",
		"value_changed": "is_email_verified",
		"condition": "doc.is_email_verified",
		"message": "They have confirmed their email and can see their order. If payment is "
		"not live yet, call them today.",
		"recipients_role": "Platform Sales",
	},
	{
		"name": "Platform Demo Request",
		"subject": "Demo request: {{ doc.organisation_name }}",
		"document_type": "Demo Request",
		"event": "New",
		"message": "A demo request has come in from the website. Time to first contact is "
		"the number that decides whether this converts.",
		"recipients_role": "Platform Sales",
	},
]


def install():
	for label, doctype, function, field, filters, colour in NUMBER_CARDS:
		if frappe.db.exists("Number Card", label):
			continue
		frappe.get_doc(
			{
				"doctype": "Number Card",
				"name": label,
				"label": label,
				"module": MODULE,
				"document_type": doctype,
				"type": "Document Type",
				"function": function,
				"aggregate_function_based_on": field,
				"filters_json": json.dumps(filters),
				"is_public": 1,
				"show_percentage_stats": 1,
				"stats_time_interval": "Monthly",
				"color": colour,
			}
		).insert(ignore_permissions=True)

	for chart in CHARTS:
		if frappe.db.exists("Dashboard Chart", chart["name"]):
			continue
		doc = dict(chart)
		doc.update(
			{
				"doctype": "Dashboard Chart",
				"module": MODULE,
				"is_public": 1,
				"filters_json": "[]",
				"dynamic_filters_json": "[]",
			}
		)
		frappe.get_doc(doc).insert(ignore_permissions=True)

	if not frappe.db.exists("Dashboard", "Platform"):
		frappe.get_doc(
			{
				"doctype": "Dashboard",
				"dashboard_name": "Platform",
				"module": MODULE,
				"cards": [{"card": label} for label, *_ in NUMBER_CARDS],
				"charts": [{"chart": chart["name"], "width": "Half"} for chart in CHARTS],
			}
		).insert(ignore_permissions=True)

	for spec in NOTIFICATIONS:
		if frappe.db.exists("Notification", spec["name"]):
			continue
		doc = dict(spec)
		role = doc.pop("recipients_role")
		if not frappe.db.exists("Role", role):
			continue
		doc.update(
			{
				"doctype": "Notification",
				"module": MODULE,
				"channel": "Email",
				"enabled": 1,
				"is_standard": 0,
				"recipients": [{"receiver_by_role": role}],
			}
		)
		frappe.get_doc(doc).insert(ignore_permissions=True)
