# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cache-busting for the portal's own scripts and stylesheets."""

import os

import frappe


def a3s_asset_version(path):
	"""The file's last change time, for `?v=` on a URL under /assets/a3_sola/.

	The site's asset version only moves on a `bench build`, so a script edited since would
	otherwise keep being served from the browser's cache. Available in every template.
	"""
	try:
		return int(os.path.getmtime(frappe.get_app_path("a3_sola", "public", path)))
	except OSError:
		return frappe.local.conf.get("asset_version") or 0
