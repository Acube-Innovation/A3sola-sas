# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""View page for one design estimate. All logic is shared; this only names the slug."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import record_route
from a3_sola.www.a3solaportal.collections import detail_context

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("design-estimates", name) if name else "/a3solaportal/design-estimates")
	detail_context(context, "design-estimates", name)
	return context
