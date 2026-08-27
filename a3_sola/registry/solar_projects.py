# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Registry for the Solar Projects module (Phase 3).

Phase 3 adds this file and nothing else to hooks.py.
"""

MODULE_NAME = "Solar Projects"

DOCTYPES = [
	"Solar Company Account Mapping",
	"Cost Category Config",
	"Project Cost Entry",
	"Solar GST Valuation Rule",
	"Billing Milestone Template",
	"Billing Milestone Template Detail",
	"Billing Milestone Entry",
	"Solar Billing Plan",
	"Statutory Fee Recovery",
	"Solar OM Contract",
	"Solar OM Coverage Item",
	"Solar OM Visit Plan",
	"Performance Log",
	"Solar OM Visit",
	"Visit Checklist Item",
	"Visit Material",
	"Service Ticket",
	"Solar Warranty Claim",
	"Generation Reading",
]

#: Everything carrying a company field. This module posts to the general ledger, so
#: isolation is load-bearing: a mis-resolved account moves one tenant's money into
#: another tenant's books.
PERMISSION_DOCTYPES = [
	"Solar GST Valuation Rule",
	"Billing Milestone Template",
	"Solar Billing Plan",
	"Statutory Fee Recovery",
	"Solar OM Contract",
	"Solar OM Visit",
	"Service Ticket",
	"Solar Warranty Claim",
	"Generation Reading",
]

DOC_EVENTS = {
	# THE ABSOLUTE RULE: no invoice may ever carry a subsidy line.
	"Sales Invoice": {
		"validate": ["a3_sola.api.billing.reject_subsidy_on_invoice"],
		"on_submit": ["a3_sola.overrides.sales_invoice.on_submit"],
		"on_cancel": ["a3_sola.overrides.sales_invoice.on_cancel"],
	},
	"Payment Entry": {
		"on_submit": ["a3_sola.overrides.payment_entry.on_submit"],
		"on_cancel": ["a3_sola.overrides.payment_entry.on_submit"],
	},
	# Contributing documents refresh the project's costs.
	"Stock Entry": {"on_submit": ["a3_sola.overrides.costing_events.refresh"]},
	"Delivery Note": {"on_submit": ["a3_sola.overrides.costing_events.refresh"]},
	"Purchase Invoice": {"on_submit": ["a3_sola.overrides.costing_events.refresh"]},
	"Installation Work Order": {"on_submit": ["a3_sola.overrides.costing_events.refresh"]},
}

SCHEDULER_EVENTS = {
	"hourly": ["a3_sola.api.sla.hourly_sla_scan"],
	"daily": [
		"a3_sola.api.om.mark_due_and_missed_visits",
		"a3_sola.api.om.detect_renewals",
	],
	"daily_long": [
		"a3_sola.api.costing.nightly_cost_refresh",
		"a3_sola.api.billing.refresh_billing_summaries",
	],
}

#: The customer portal. One page, login required, ownership derived from the session on
#: every request - there is no id in the route to manipulate.
PORTAL_MENU_ITEMS = [
	{"title": "My Solar System", "route": "/solar", "reference_doctype": "", "role": "Customer"},
]

FIXTURES = [
	{"dt": "Custom Field", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Property Setter", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Notification", "filters": [["module", "=", MODULE_NAME]]},
]
