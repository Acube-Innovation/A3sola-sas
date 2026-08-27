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

# --- assembled from the per-module registries -------------------------------
doc_events = registry.merged_doc_events()
scheduler_events = registry.merged_scheduler_events()
fixtures = registry.merged_fixtures()
permission_query_conditions = registry.permission_query_conditions()
has_permission = registry.has_permission_map()
standard_portal_menu_items = registry.merged_portal_menu_items()
update_website_context = registry.merged_website_context()
website_route_rules = registry.merged_website_route_rules()

jinja = {
	"methods": [
		"a3_sola.api.proposal.proposal_context",
	],
}
