# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Solar CRM dashboard, notifications and workflows.

The number cards and charts reproduce the client's existing lead-tracker dashboard first -
total leads, converted, overdue follow-ups, total pipeline kW, the lead status breakdown
and the initial call connectivity breakdown - then extend it. Switching from the
spreadsheet to ERPNext must not lose a number they already look at.
"""

import json

import frappe

MODULE = "Solar CRM"

NUMBER_CARDS = [
	# label, doctype, function, aggregate field, filters, colour
	("Total Leads Ingested", "Lead", "Count", None, [], "Blue"),
	("Converted / Won", "Lead", "Count", None, [["solar_lead_status", "=", "Converted / Won"]], "Green"),
	("Overdue Follow-ups", "Lead", "Count", None, [["followup_status", "=", "FOLLOW UP DUE"]], "Red"),
	("Total Pipeline kW", "Lead", "Sum", "approx_capacity_kw", [["solar_lead_status", "not in", ["Closed / Unresponsive", "Not Interested"]]], "Purple"),
	("Surveys Pending Review", "Site Survey", "Count", None, [["docstatus", "=", 0]], "Orange"),
	("Designs Awaiting Proposal", "Solar Design Estimate", "Count", None, [["docstatus", "=", 1]], "Blue"),
	("Proposals Sent This Month", "Solar Proposal", "Count", None, [["status", "=", "Sent"]], "Green"),
	("kW Quoted This Month", "Solar Design Estimate", "Sum", "final_capacity_kw", [["docstatus", "=", 1]], "Purple"),
]

CHARTS = [
	{
		"name": "Lead Status Breakdown",
		"chart_name": "Lead Status Breakdown",
		"chart_type": "Group By",
		"document_type": "Lead",
		"group_by_type": "Count",
		"group_by_based_on": "solar_lead_status",
		"type": "Donut",
		"number_of_groups": 7,
	},
	{
		"name": "Initial Call Connectivity",
		"chart_name": "Initial Call Connectivity",
		"chart_type": "Group By",
		"document_type": "Lead",
		"group_by_type": "Count",
		"group_by_based_on": "call_status",
		"type": "Donut",
		"number_of_groups": 4,
	},
	{
		"name": "Outreach Stage Distribution",
		"chart_name": "Outreach Stage Distribution",
		"chart_type": "Group By",
		"document_type": "Lead",
		"group_by_type": "Count",
		"group_by_based_on": "outreach_stage",
		"type": "Bar",
		"number_of_groups": 5,
	},
	{
		"name": "Proposals by Package",
		"chart_name": "Proposals by Package",
		"chart_type": "Group By",
		"document_type": "Solar Proposal",
		"group_by_type": "Count",
		"group_by_based_on": "capacity_label",
		"type": "Pie",
		"number_of_groups": 8,
	},
	{
		"name": "Monthly kW Quoted",
		"chart_name": "Monthly kW Quoted",
		"chart_type": "Sum",
		"document_type": "Solar Design Estimate",
		"based_on": "estimate_date",
		"value_based_on": "final_capacity_kw",
		"timespan": "Last Year",
		"time_interval": "Monthly",
		"type": "Bar",
	},
]

NOTIFICATIONS = [
	{
		"name": "Solar Survey Submitted",
		"subject": "Site Survey {{ doc.name }} submitted for {{ doc.customer_name }}",
		"document_type": "Site Survey",
		"event": "Submit",
		"message": "A site survey has been submitted and is ready for design.",
		"recipients_role": "Solar Design Engineer",
	},
	{
		"name": "Solar Design Estimate Approved",
		"subject": "Design estimate {{ doc.name }} submitted",
		"document_type": "Solar Design Estimate",
		"event": "Submit",
		"message": "The design estimate is submitted and a proposal can be raised.",
		"recipients_role": "Solar Sales Executive",
	},
	{
		"name": "Solar Eligibility Not Eligible",
		"subject": "Eligibility check {{ doc.name }} returned Not Eligible",
		"document_type": "Subsidy Eligibility Check",
		"event": "Value Change",
		"value_changed": "overall_result",
		"condition": 'doc.overall_result == "Not Eligible"',
		"message": "This job failed one or more subsidy eligibility rules. Review the failing "
		"rules and either resolve them or record a waiver.",
		"recipients_role": "Solar Sales Manager",
	},
]


def _exists(doctype, name):
	return frappe.db.exists(doctype, name)


def install():
	"""Create dashboard, cards, charts and notifications. Idempotent."""
	create_number_cards()
	create_charts()
	create_dashboard()
	create_notifications()


def create_number_cards():
	for label, doctype, function, field, filters, colour in NUMBER_CARDS:
		if _exists("Number Card", label):
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


def create_charts():
	for chart in CHARTS:
		if _exists("Dashboard Chart", chart["name"]):
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


def create_dashboard():
	name = "Solar CRM"
	if _exists("Dashboard", name):
		return
	frappe.get_doc(
		{
			"doctype": "Dashboard",
			"dashboard_name": name,
			"module": MODULE,
			"is_default": 0,
			"is_standard": 0,
			"cards": [{"card": label} for label, *_ in NUMBER_CARDS],
			"charts": [{"chart": chart["name"], "width": "Half"} for chart in CHARTS],
		}
	).insert(ignore_permissions=True)


def create_notifications():
	for spec in NOTIFICATIONS:
		if _exists("Notification", spec["name"]):
			continue
		doc = dict(spec)
		role = doc.pop("recipients_role")
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
