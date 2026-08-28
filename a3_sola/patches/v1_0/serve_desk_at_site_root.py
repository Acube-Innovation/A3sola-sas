# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Give `/` back to the desk.

The public pages used to sit at `www/`, so Frappe served the marketing homepage at the site
root and signing in to the ERP meant getting past a landing page first. They now live under
`www/a3sola/`, which frees `/` - but an existing site still has `home_page` pointing at the
old index, so it needs saying explicitly.

Only touches a site that never set one deliberately. Somebody who has chosen their own home
page meant it.
"""

import frappe


def execute():
	settings = frappe.get_single("Website Settings")
	if settings.home_page not in (None, "", "index", "home"):
		return None
	settings.home_page = "app"
	settings.flags.ignore_permissions = True
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.clear_cache()
	return settings.home_page
