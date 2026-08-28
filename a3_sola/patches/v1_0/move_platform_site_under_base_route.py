# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Move the stored detail-page routes under the configured base.

Feature and solution detail pages are web views: each record carries its own `route`, and
that route is data, not code. So changing where the public site lives moves the templates
but leaves every detail page answering on its old URL - which is worse than not moving at
all, because half the site is then in one place and half in another.

Idempotent, and safe to run when the base is empty: it strips a stale prefix as readily as
it adds a missing one, so switching the site back to the root is the same patch.
"""

import frappe


def execute():
	from a3_sola.api.platform import base_route

	base = base_route()
	moved = 0
	for doctype, prefix in (("Platform Feature", "features"), ("Platform Solution", "solutions")):
		if not frappe.db.exists("DocType", doctype):
			continue
		for row in frappe.get_all(doctype, fields=["name", "route"]):
			wanted = _wanted(row.route, prefix, base)
			if wanted and wanted != row.route:
				frappe.db.set_value(doctype, row.name, "route", wanted, update_modified=False)
				moved += 1
	if moved:
		frappe.db.commit()
		frappe.clear_cache()
	return moved


def _wanted(route, prefix, base):
	"""The route this record should hold, given the base the site is configured with."""
	route = (route or "").strip("/")
	if not route:
		return None
	# Strip whatever base is currently on it - the setting may have changed more than once,
	# and a route is only ever `<base>/<prefix>/<slug>` or `<prefix>/<slug>`.
	parts = route.split("/")
	while parts and parts[0] != prefix:
		parts.pop(0)
	if not parts:
		return None
	tail = "/".join(parts)
	return f"{base}/{tail}" if base else tail
