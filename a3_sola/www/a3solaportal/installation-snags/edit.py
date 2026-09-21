# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Edit page for one snag. All logic is shared; this only names the slug."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import edit_context, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("installation-snags", name) + "/edit" if name else "/a3solaportal/installation-snags")
	edit_context(context, "installation-snags", name)
	return context
