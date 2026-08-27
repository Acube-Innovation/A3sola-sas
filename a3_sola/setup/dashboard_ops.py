# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Solar Operations dashboard and notifications."""

import json

import frappe

MODULE = "Solar Operations"

NUMBER_CARDS = [
	("Installations In Progress", "Solar Installation", "Count", None,
	 [["status", "in", ["In Progress", "Blocked", "Awaiting External"]], ["docstatus", "=", 1]], "Blue"),
	("Awaiting External Approval", "Solar Installation", "Count", None,
	 [["status", "=", "Awaiting External"], ["docstatus", "=", 1]], "Orange"),
	("SLA Breached", "Solar Installation", "Count", None,
	 [["is_sla_breached", "=", 1], ["docstatus", "=", 1]], "Red"),
	("kW Commissioned", "Solar Installation", "Sum", "capacity_kw",
	 [["status", "in", ["Commissioned", "Subsidy Claimed", "Closed"]], ["docstatus", "=", 1]], "Green"),
	("Open Critical Snags", "Installation Snag", "Count", None,
	 [["severity", "=", "Critical"], ["status", "in", ["Open", "In Progress"]]], "Red"),
	("Documents Stale", "Solar Installation", "Sum", "stale_document_count",
	 [["docstatus", "=", 1]], "Orange"),
	("Subsidy Claims Pending", "Subsidy Claim", "Count", None,
	 [["claim_status", "in", ["PCR Uploaded", "Under Verification", "Approved"]], ["docstatus", "=", 1]], "Blue"),
	("Outstanding Subsidy Recovery", "Subsidy Claim", "Sum", "outstanding_recovery",
	 [["docstatus", "=", 1]], "Purple"),
	("Registration Refunds Outstanding", "Statutory Fee Payment", "Sum", "refundable_amount",
	 [["refund_status", "in", ["Due", "Claimed"]], ["docstatus", "=", 1]], "Purple"),
	("Loan Balance Outstanding", "Loan Application", "Sum", "outstanding",
	 [["docstatus", "=", 1]], "Purple"),
]

CHARTS = [
	{
		"name": "Installations by Current Stage",
		"chart_name": "Installations by Current Stage",
		"chart_type": "Group By",
		"document_type": "Solar Installation",
		"group_by_type": "Count",
		"group_by_based_on": "current_stage",
		"type": "Bar",
		"number_of_groups": 10,
	},
	{
		"name": "Installations by Status",
		"chart_name": "Installations by Status",
		"chart_type": "Group By",
		"document_type": "Solar Installation",
		"group_by_type": "Count",
		"group_by_based_on": "status",
		"type": "Donut",
		"number_of_groups": 8,
	},
	{
		"name": "Blocking Party",
		"chart_name": "Blocking Party",
		"chart_type": "Group By",
		"document_type": "Solar Installation",
		"group_by_type": "Count",
		"group_by_based_on": "blocking_party",
		"type": "Donut",
		"number_of_groups": 6,
	},
	{
		"name": "Monthly Commissioned Capacity",
		"chart_name": "Monthly Commissioned Capacity",
		"chart_type": "Sum",
		"document_type": "Solar Installation",
		"based_on": "warranty_start_date",
		"value_based_on": "capacity_kw",
		"timespan": "Last Year",
		"time_interval": "Monthly",
		"type": "Bar",
	},
	{
		"name": "Snags by Category",
		"chart_name": "Snags by Category",
		"chart_type": "Group By",
		"document_type": "Installation Snag",
		"group_by_type": "Count",
		"group_by_based_on": "category",
		"type": "Bar",
		"number_of_groups": 10,
	},
]

NOTIFICATIONS = [
	{
		"name": "Solar Stage SLA Breached",
		"subject": "SLA breached on {{ doc.name }} - {{ doc.current_stage }}",
		"document_type": "Solar Installation",
		"event": "Value Change",
		"value_changed": "is_sla_breached",
		"condition": "doc.is_sla_breached",
		"message": "This installation has breached the SLA on its current stage. "
		"Check the External Dependency Ageing report and chase the named Assistant Engineer.",
		"recipients_role": "Solar Operations Manager",
	},
	{
		"name": "Solar Portal Query Raised",
		"subject": "Query raised on {{ doc.name }}",
		"document_type": "Portal Application",
		"event": "Value Change",
		"value_changed": "application_status",
		"condition": 'doc.application_status == "Query Raised"',
		"message": "The DISCOM or the portal has raised a query. The mapped installation stage is "
		"blocked until it is resolved.",
		"recipients_role": "Solar Liaison Officer",
	},
	{
		"name": "Solar Critical Snag Raised",
		"subject": "Critical snag {{ doc.name }} on {{ doc.solar_installation }}",
		"document_type": "Installation Snag",
		"event": "New",
		"condition": 'doc.severity == "Critical"',
		"message": "A critical defect has been raised. Unresolved defects are a vendor "
		"registration risk, not just a quality issue.",
		"recipients_role": "Solar Operations Manager",
	},
	{
		"name": "Solar Commissioning Submitted",
		"subject": "{{ doc.solar_installation }} commissioned",
		"document_type": "Commissioning Report",
		"event": "Submit",
		"message": "The installation is commissioned. The warranty window is set and the "
		"five-year O&M obligation starts today.",
		"recipients_role": "Accounts Manager",
	},
	{
		"name": "Solar Subsidy Disbursed",
		"subject": "Subsidy disbursed on {{ doc.name }}",
		"document_type": "Subsidy Claim",
		"event": "Value Change",
		"value_changed": "claim_status",
		"condition": 'doc.claim_status == "Disbursed"',
		"message": "The subsidy has reached the customer. Where the company funded the gap, "
		"recovery is now due.",
		"recipients_role": "Accounts Manager",
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

	if not frappe.db.exists("Dashboard", "Solar Operations"):
		frappe.get_doc(
			{
				"doctype": "Dashboard",
				"dashboard_name": "Solar Operations",
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
