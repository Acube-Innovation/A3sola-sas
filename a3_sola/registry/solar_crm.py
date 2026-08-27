# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Registry for the Solar CRM module (Phase 1)."""

MODULE_NAME = "Solar CRM"

#: Every doctype this module owns.
DOCTYPES = [
	"A3 Sola Settings",
	"DISCOM",
	"DISCOM Section",
	"Roof Type",
	"Subsidy Scheme",
	"Subsidy Slab",
	"Electricity Tariff",
	"Tariff Slab",
	"Statutory Fee Schedule",
	"Net Meter Charge",
	"Grid Regulation Rule",
	"Component Make",
	"Scope Of Work Item",
	"Brand Link",
	"Outreach Cadence Step",
	"Outreach Message Template",
	"Solar Package",
	"Solar Package Component",
	"Solar Consumer",
	"Site Survey",
	"Roof Segment",
	"Shadow Observation",
	"Survey Image",
	"EHS Checklist Item",
	"Solar Design Estimate",
	"Design Estimate Option",
	"Cashflow Projection",
	"Subsidy Eligibility Check",
	"Eligibility Rule Result",
	"Solar Proposal",
	"Outreach Log",
]

#: Doctypes that carry a company field and therefore need tenant isolation hooks.
#: Child tables are excluded - they are reached through their parent, which is guarded.
#: A3 Sola Settings is excluded because a Single has no company.
PERMISSION_DOCTYPES = [
	"DISCOM",
	"DISCOM Section",
	"Roof Type",
	"Subsidy Scheme",
	"Electricity Tariff",
	"Statutory Fee Schedule",
	"Grid Regulation Rule",
	"Component Make",
	"Outreach Message Template",
	"Solar Package",
	"Solar Consumer",
	"Site Survey",
	"Solar Design Estimate",
	"Subsidy Eligibility Check",
	"Solar Proposal",
]

DOC_EVENTS = {
	"Lead": {
		"validate": ["a3_sola.overrides.lead.validate"],
	},
	"Opportunity": {
		"validate": ["a3_sola.overrides.opportunity.validate"],
	},
	"Quotation": {
		"validate": ["a3_sola.overrides.quotation.validate"],
		"on_submit": ["a3_sola.overrides.quotation.on_submit"],
	},
	"Sales Order": {
		"on_submit": ["a3_sola.overrides.sales_order.on_submit"],
	},
	"Company": {
		"validate": ["a3_sola.overrides.company.validate"],
	},
}

SCHEDULER_EVENTS = {
	"daily": [
		"a3_sola.api.outreach.daily_followup_scan",
	],
}

#: Module-filtered so `bench export-fixtures` does not drag unrelated records in.
FIXTURES = [
	{"dt": "Custom Field", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Property Setter", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Role", "filters": [["name", "like", "Solar %"]]},
	{"dt": "Workflow", "filters": [["name", "like", "Solar %"]]},
	{"dt": "Workflow State", "filters": [["name", "like", "Solar %"]]},
	{"dt": "Workflow Action Master", "filters": [["name", "like", "Solar %"]]},
	{"dt": "Notification", "filters": [["module", "=", MODULE_NAME]]},
]
