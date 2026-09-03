# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""a3_sola hooks.

One app, four modules — Solar CRM, Solar Operations, Solar Projects, Platform.

This file is deliberately thin and stays that way. Everything a module contributes —
doctypes, doc events, permission hooks, schedulers and fixtures — is declared in its own
registry file under `a3_sola/registry/` and merged here. Every later phase adds a registry
file and nothing else to this file.
"""

from a3_sola import registry

app_name = "a3_sola"
app_title = "A3 Sola"
app_publisher = "Acube Innovations"
app_description = "Solar EPC business application for ERPNext: Solar CRM, Solar Operations, Solar Projects and Platform"
app_email = "saaspurchases@acube.co"
app_license = "mit"

required_apps = ["frappe/erpnext"]

app_include_js = "a3_sola.bundle.js"

after_install = "a3_sola.setup.install.after_install"
after_migrate = "a3_sola.setup.install.after_migrate"

# Defence in depth for a suspended tenant. Disabling users is the primary mechanism; these
# catch the doors that do not go through a login - an API key, a token, a session that was
# already open. Both are cheap: one cached lookup per request, cleared on any state change.
# See a3_sola/api/lifecycle/gate.py, which also holds the allowlist that guarantees a
# suspended customer can always reach the page that ends their suspension.
before_request = ["a3_sola.api.lifecycle.gate.enforce"]
on_session_creation = ["a3_sola.api.lifecycle.gate.on_session_creation"]

# A heartbeat around every scheduled job, recorded here rather than by decorating fifteen
# functions - because the sixteenth job is the one that would be added without one, and
# the sixteenth job is exactly the one that stops silently.
before_job = ["a3_sola.api.monitoring.heartbeat.on_job_start"]
after_job = ["a3_sola.api.monitoring.heartbeat.on_job_end"]

# --- assembled from the per-module registries -------------------------------
doc_events = registry.merged_doc_events()
scheduler_events = registry.merged_scheduler_events()
fixtures = registry.merged_fixtures()
permission_query_conditions = registry.permission_query_conditions()
has_permission = registry.has_permission_map()
standard_portal_menu_items = registry.merged_portal_menu_items()
update_website_context = registry.merged_website_context()
website_route_rules = registry.merged_website_route_rules()

# Connections panels for the ERPNext doctypes the solar chain passes through.
# Each of these extends ERPNext's own dashboard rather than replacing it.
override_doctype_dashboards = {
	"Lead": ["a3_sola.dashboards.get_lead_dashboard_data"],
	"Project": ["a3_sola.dashboards.get_project_dashboard_data"],
	"Quotation": ["a3_sola.dashboards.get_quotation_dashboard_data"],
	"Sales Order": ["a3_sola.dashboards.get_sales_order_dashboard_data"],
	"Sales Invoice": ["a3_sola.dashboards.get_sales_invoice_dashboard_data"],
}

jinja = {
	"methods": [
		"a3_sola.api.proposal.proposal_context",
	],
}
