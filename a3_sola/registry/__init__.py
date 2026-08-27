# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Per-module registries, merged into hooks.py.

hooks.py is shared across all four modules and must not become an unmaintainable blob, so
each module exports DOCTYPES, DOC_EVENTS, PERMISSION_DOCTYPES, SCHEDULER_EVENTS and
FIXTURES from a registry file here, and hooks.py merges them. Every later phase adds a
registry file and nothing else to hooks.py.
"""

from a3_sola.registry import platform, solar_crm, solar_operations, solar_projects

MODULES = [solar_crm, solar_operations, solar_projects, platform]


def all_doctypes():
	out = []
	for module in MODULES:
		out.extend(getattr(module, "DOCTYPES", []))
	return out


def all_permission_doctypes():
	out = []
	for module in MODULES:
		out.extend(getattr(module, "PERMISSION_DOCTYPES", []))
	return out


def merged_doc_events():
	merged = {}
	for module in MODULES:
		for doctype, events in getattr(module, "DOC_EVENTS", {}).items():
			target = merged.setdefault(doctype, {})
			for event, handlers in events.items():
				existing = target.setdefault(event, [])
				if isinstance(handlers, str):
					handlers = [handlers]
				existing.extend(handlers)
	return merged


def merged_scheduler_events():
	merged = {}
	for module in MODULES:
		for cadence, handlers in getattr(module, "SCHEDULER_EVENTS", {}).items():
			merged.setdefault(cadence, []).extend(handlers)
	return merged


def merged_website_route_rules():
	out = []
	for module in MODULES:
		out.extend(getattr(module, "WEBSITE_ROUTE_RULES", []))
	return out


def merged_website_context():
	out = []
	for module in MODULES:
		out.extend(getattr(module, "WEBSITE_CONTEXT", []))
	return out


def merged_portal_menu_items():
	out = []
	for module in MODULES:
		out.extend(getattr(module, "PORTAL_MENU_ITEMS", []))
	return out


def merged_fixtures():
	out = []
	for module in MODULES:
		out.extend(getattr(module, "FIXTURES", []))
	return out


#: Frappe pickles the hooks dict into the cache, so hook values must be dotted-path
#: strings rather than callables. One shared implementation serves every doctype -
#: Frappe passes the doctype on each call.
QUERY_CONDITIONS_METHOD = "a3_sola.api.permissions.query_conditions"
HAS_PERMISSION_METHOD = "a3_sola.api.permissions.has_company_permission"


def permission_query_conditions():
	"""Bind the shared query-condition implementation to every registered doctype."""
	return {dt: QUERY_CONDITIONS_METHOD for dt in all_permission_doctypes()}


def has_permission_map():
	"""Bind the shared row-level check to every registered doctype."""
	return {dt: HAS_PERMISSION_METHOD for dt in all_permission_doctypes()}
