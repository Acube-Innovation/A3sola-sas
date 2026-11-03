# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One Solar Package, edited whole: its details and every table of the desk form, its payment
terms, and its Item and BOM (api/portal_packages). `?name=` edits one, `?copy=` starts a new
one from another, neither adds a new one. Admins only."""

import frappe

from a3_sola.api import portal_packages
from a3_sola.api.portal_users import require_admin
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	args = frappe.form_dict
	require_login("/a3solaportal/packages/edit" + ("?name=" + args.name if args.get("name") else ""))
	require_admin()
	data = portal_packages.package(name=args.get("name") or None, copy_from=args.get("copy") or None)
	title = data["title"] if data["name"] else ("New package" if not args.get("copy") else data["title"])
	fill_shell(
		context,
		active_route="/a3solaportal/packages",
		page_title=title,
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Packages", "href": "/a3solaportal/packages"}, {"label": title}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.data = data
	context.page_name = title
	return context
