# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Registry for the Solar Operations module (Phase 2).

Phase 2 adds this file and nothing else to hooks.py.
"""

MODULE_NAME = "Solar Operations"

DOCTYPES = [
	"Installation Stage Template",
	"Installation Stage Template Detail",
	"Document Checklist Template",
	"Document Checklist Template Item",
	"Solar Document Template",
	"Document Template Set",
	"Document Template Set Item",
	"Generated Document Log",
	"Solar Installation",
	"Installation Stage Log",
	"Installation Document",
	"Installation Serial Register",
	"Portal Application",
	"Application Query",
	"Loan Application",
	"Loan Disbursement",
	"Installation Work Order",
	"Work Order Crew",
	"Work Log",
	"Commissioning Report",
	"Test Reading",
	"Inverter Protection Setting",
	"Net Metering Agreement",
	"Wheeling Preference",
	"Installation Snag",
	"Subsidy Claim",
	"Statutory Fee Payment",
]

#: Doctypes carrying a company field, so they need tenant isolation hooks.
#: Child tables are excluded - they are reached through a guarded parent.
PERMISSION_DOCTYPES = [
	"Installation Stage Template",
	"Document Checklist Template",
	"Solar Document Template",
	"Document Template Set",
	"Solar Installation",
	"Portal Application",
	"Loan Application",
	"Installation Work Order",
	"Commissioning Report",
	"Net Metering Agreement",
	"Installation Snag",
	"Subsidy Claim",
	"Statutory Fee Payment",
]

DOC_EVENTS = {
	# An edited consumer number must visibly invalidate the letters that carried it.
	"Solar Consumer": {"on_update": ["a3_sola.api.documents.mark_stale_on_change"]},
	"Solar Installation": {"on_update": ["a3_sola.api.documents.mark_stale_on_change"]},
	"Company": {"on_update": ["a3_sola.api.documents.mark_stale_on_change"]},
	"Delivery Note": {"on_submit": ["a3_sola.overrides.delivery_note.on_submit"]},
}

SCHEDULER_EVENTS = {
	"daily": ["a3_sola.api.escalation.daily_escalation"],
}

FIXTURES = [
	{"dt": "Custom Field", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Property Setter", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Notification", "filters": [["module", "=", MODULE_NAME]]},
]
