# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Solar Projects dashboard and notifications.

Two audiences share this module and they read different numbers: finance reads margin,
receivables and unbilled work; O&M reads visits, tickets and the performance obligation.
Both sets are here because both are the same project - what a job cost and what it now
owes in service are not separable questions.
"""

import json

import frappe

MODULE = "Solar Projects"

NUMBER_CARDS = [
	# Finance.
	("Projects In Delivery", "Project", "Count", None,
	 [["status", "=", "Open"], ["solar_installation", "is", "set"]], "Blue"),
	("Contract Value In Hand", "Solar Billing Plan", "Sum", "gross_contract_value",
	 [["docstatus", "=", 1]], "Blue"),
	("Unbilled Balance", "Solar Billing Plan", "Sum", "unbilled_balance",
	 [["docstatus", "=", 1]], "Orange"),
	("Outstanding From Customers", "Solar Billing Plan", "Sum", "total_outstanding",
	 [["docstatus", "=", 1]], "Red"),
	("Statutory Reimbursement Outstanding", "Solar Billing Plan", "Sum", "statutory_outstanding",
	 [["docstatus", "=", 1]], "Purple"),
	# O&M.
	("Live O&M Contracts", "Solar OM Contract", "Count", None,
	 [["status", "=", "Active"], ["docstatus", "=", 1]], "Green"),
	("kWp Under Maintenance", "Solar OM Contract", "Sum", "capacity_kw",
	 [["status", "=", "Active"], ["docstatus", "=", 1]], "Green"),
	("Open Service Tickets", "Service Ticket", "Count", None,
	 [["status", "not in", ["Resolved", "Closed"]], ["docstatus", "=", 1]], "Orange"),
	("Escalated Tickets", "Service Ticket", "Count", None,
	 [["escalation_level", ">", 0], ["status", "not in", ["Resolved", "Closed"]],
	  ["docstatus", "=", 1]], "Red"),
	("Performance Obligation Breached", "Solar OM Contract", "Count", None,
	 [["performance_obligation_status", "=", "Breached"], ["docstatus", "=", 1]], "Red"),
	("O&M Provision Balance", "Solar OM Contract", "Sum", "om_provision_balance",
	 [["docstatus", "=", 1]], "Purple"),
	("Warranty Claims Open", "Solar Warranty Claim", "Count", None,
	 [["claim_status", "not in", ["Replaced", "Rejected", "Closed"]], ["docstatus", "=", 1]], "Orange"),
]

CHARTS = [
	{
		"name": "Project Margin by Capacity Band",
		"chart_name": "Project Margin by Capacity Band",
		"chart_type": "Group By",
		"document_type": "Project",
		"group_by_type": "Sum",
		"group_by_based_on": "solar_package",
		"aggregate_function_based_on": "gross_margin_amount",
		"type": "Bar",
		"number_of_groups": 10,
	},
	{
		"name": "Monthly Billing",
		"chart_name": "Monthly Billing",
		"chart_type": "Sum",
		"document_type": "Sales Invoice",
		"based_on": "posting_date",
		"value_based_on": "grand_total",
		"timespan": "Last Year",
		"time_interval": "Monthly",
		"type": "Bar",
	},
	{
		"name": "Service Tickets by Category",
		"chart_name": "Service Tickets by Category",
		"chart_type": "Group By",
		"document_type": "Service Ticket",
		"group_by_type": "Count",
		"group_by_based_on": "category",
		"type": "Bar",
		"number_of_groups": 10,
	},
	{
		"name": "Service Tickets by Root Cause",
		"chart_name": "Service Tickets by Root Cause",
		"chart_type": "Group By",
		"document_type": "Service Ticket",
		"group_by_type": "Count",
		"group_by_based_on": "root_cause",
		"type": "Donut",
		"number_of_groups": 8,
	},
	{
		"name": "Performance Obligation Status",
		"chart_name": "Performance Obligation Status",
		"chart_type": "Group By",
		"document_type": "Solar OM Contract",
		"group_by_type": "Count",
		"group_by_based_on": "performance_obligation_status",
		"type": "Donut",
		"number_of_groups": 5,
	},
	{
		"name": "Warranty Claims by Component",
		"chart_name": "Warranty Claims by Component",
		"chart_type": "Group By",
		"document_type": "Solar Warranty Claim",
		"group_by_type": "Count",
		"group_by_based_on": "component_type",
		"type": "Bar",
		"number_of_groups": 8,
	},
]

NOTIFICATIONS = [
	{
		"name": "Solar Milestone Ready to Invoice",
		"subject": "Milestone triggered on {{ doc.name }}",
		"document_type": "Solar Billing Plan",
		"event": "Value Change",
		"value_changed": "total_triggered",
		"message": "A billing milestone has been triggered by site progress. Raise the invoice "
		"from the billing plan - it is created as a draft for review, never posted automatically.",
		"recipients_role": "Accounts Manager",
	},
	{
		"name": "Solar Performance Obligation Breached",
		"subject": "Performance breach on {{ doc.name }}",
		"document_type": "Solar OM Contract",
		"event": "Value Change",
		"value_changed": "performance_obligation_status",
		"condition": 'doc.performance_obligation_status == "Breached"',
		"message": "The performance ratio has fallen below the contractual floor. This is a "
		"clause in a signed agreement, so it is a contractual exposure and not a service "
		"observation - a Critical ticket has been raised alongside this notice.",
		"recipients_role": "Solar O&M Manager",
	},
	{
		"name": "Solar Critical Service Ticket",
		"subject": "Critical ticket {{ doc.name }}",
		"document_type": "Service Ticket",
		"event": "New",
		"condition": 'doc.severity == "Critical"',
		"message": "A critical service ticket has been raised. A complaint left unaddressed is "
		"a vendor registration risk under the scheme's grievance framework.",
		"recipients_role": "Solar O&M Manager",
	},
	{
		"name": "Solar Warranty Claim Rejected",
		"subject": "Warranty claim {{ doc.name }} rejected",
		"document_type": "Solar Warranty Claim",
		"event": "Value Change",
		"value_changed": "claim_status",
		"condition": 'doc.claim_status == "Rejected"',
		"message": "The manufacturer has rejected this claim. The replacement cost now sits "
		"with the company unless the rejection is challenged.",
		"recipients_role": "Solar O&M Manager",
	},
	{
		"name": "Solar O&M Contract Expiring",
		"subject": "O&M contract {{ doc.name }} is expiring",
		"document_type": "Solar OM Contract",
		"event": "Value Change",
		"value_changed": "status",
		"condition": 'doc.status == "Expiring"',
		"message": "This contract is inside its renewal window. The site is known, the "
		"performance history is on file - see the Renewal Pipeline report.",
		"recipients_role": "Solar Sales Manager",
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

	if not frappe.db.exists("Dashboard", "Solar Projects"):
		frappe.get_doc(
			{
				"doctype": "Dashboard",
				"dashboard_name": "Solar Projects",
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
