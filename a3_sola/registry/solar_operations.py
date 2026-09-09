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
	"Solar Agreement",
	"Wheeling Preference",
	"Installation Task",
	"Task Attachment",
	"Task Generated Document",
	"Solar Contractor",
	"Work Order Type Item",
	"Site Photo",
	"Material Dispatch Notice",
	"Document Pack",
	"Company Support Contact",
	"Customer Review",
	"Review Media",
	"Subsidy Correction",
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
	"Solar Agreement",
	"Installation Task",
	"Solar Contractor",
	"Material Dispatch Notice",
	"Document Pack",
	"Customer Review",
	"Installation Snag",
	"Subsidy Claim",
	"Statutory Fee Payment",
]

#: The one hook that lets a task's document drive the task's row on the installation.
_SYNC = "a3_sola.api.tasks.sync_from_document"
_SYNC_EVENTS = {
	"on_update": [_SYNC], "on_submit": [_SYNC], "on_update_after_submit": [_SYNC], "on_cancel": [_SYNC],
	# A deleted task document lets go of its row; the installation must never point at nothing.
	"on_trash": [_SYNC],
}

#: Every doctype a task is carried out in. Adding a task doctype means adding it here and
#: to `api.tasks.TASK_DOCTYPES`; nothing else.
TASK_DOCTYPES = (
	"Installation Task",
	"Portal Application",
	"Loan Application",
	"Solar Agreement",
	"Installation Work Order",
	"Statutory Fee Payment",
	"Commissioning Report",
	"Subsidy Claim",
	"Document Pack",
	"Material Dispatch Notice",
	"Customer Review",
	"Purchase Order",
)

DOC_EVENTS = {
	# An edited consumer number must visibly invalidate the letters that carried it.
	"Solar Consumer": {"on_update": ["a3_sola.api.documents.mark_stale_on_change"]},
	"Solar Installation": {"on_update": ["a3_sola.api.documents.mark_stale_on_change"]},
	"Company": {"on_update": ["a3_sola.api.documents.mark_stale_on_change"]},
	"Delivery Note": {
		"on_update": [_SYNC],
		"on_submit": ["a3_sola.overrides.delivery_note.on_submit", _SYNC],
		"on_update_after_submit": [_SYNC],
		"on_cancel": [_SYNC],
	},
	# The order is linked to its task by the handoff; only its cancellation needs the hook.
	"Sales Order": {"on_cancel": [_SYNC]},
	**{doctype: dict(_SYNC_EVENTS) for doctype in TASK_DOCTYPES},
	# The purchase order carries the site to the supplier and files its own print.
	"Purchase Receipt": {"on_submit": ["a3_sola.api.documents.register_erpnext_document"]},
}
DOC_EVENTS["Purchase Order"]["validate"] = ["a3_sola.api.materials.set_site_fields"]
DOC_EVENTS["Purchase Order"]["on_submit"] = DOC_EVENTS["Purchase Order"]["on_submit"] + [
	"a3_sola.api.documents.register_erpnext_document"
]

SCHEDULER_EVENTS = {
	"daily": ["a3_sola.api.escalation.daily_escalation"],
}

FIXTURES = [
	{"dt": "Custom Field", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Property Setter", "filters": [["module", "=", MODULE_NAME]]},
	{"dt": "Notification", "filters": [["module", "=", MODULE_NAME]]},
]
