# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Administration > Menu: an admin chooses which items of the portal's left menu are shown.

An item ticked off is hidden from everyone's menu - admins' too - and a group left with none
is not shown at all. It is hidden only: its page still opens by its link, whoever may read
it, and the desk is unchanged. The menu itself is single-sourced in
www/a3solaportal.NAV_GROUPS; the hidden routes are kept in A3 Sola Settings
(hidden_portal_menu, one per line). This page is never hidden, so the menu can always be
put back.
"""

import json

import frappe
from frappe import _

from a3_sola.api.portal_users import require_admin

SETTINGS = "A3 Sola Settings"
FIELD = "hidden_portal_menu"
ROUTE = "/a3solaportal/menu"
#: Never hidden: the page that brings the rest back.
ALWAYS_SHOWN = {ROUTE}


def hidden():
	"""The routes hidden from the menu."""
	value = frappe.db.get_single_value(SETTINGS, FIELD) or ""
	return {line.strip() for line in value.splitlines() if line.strip()} - ALWAYS_SHOWN


def menu():
	"""Every group of the menu, each item with whether it is shown (and whether it may be hidden)."""
	from a3_sola.www.a3solaportal import NAV_GROUPS

	off = hidden()
	return [{"key": g["key"], "label": g["label"], "items": [{
		"title": i["title"], "sub": i["sub"], "ic": i["ic"], "route": i["route"],
		"shown": i["route"] not in off, "locked": i["route"] in ALWAYS_SHOWN,
	} for i in g["items"]]} for g in NAV_GROUPS]


@frappe.whitelist(methods=["POST"])
def save(hidden_routes=None):
	"""Hide `hidden_routes` (a list of menu routes) from the menu, and show every other item."""
	require_admin()
	from a3_sola.www.a3solaportal import NAV_GROUPS

	routes = json.loads(hidden_routes) if isinstance(hidden_routes, str) else hidden_routes or []
	known = {i["route"] for g in NAV_GROUPS for i in g["items"]}
	unknown = [r for r in routes if r not in known]
	if unknown:
		frappe.throw(_("Not menu items: {0}").format(", ".join(unknown)))
	value = "\n".join(sorted(set(routes) - ALWAYS_SHOWN))
	frappe.db.set_single_value(SETTINGS, FIELD, value)
	return menu()
