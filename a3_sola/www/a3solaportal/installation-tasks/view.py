# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one task. All logic is shared; this only names the slug."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("installation-tasks", name) if name else "/a3solaportal/installation-tasks")
	detail_context(context, "installation-tasks", name)
	return context
