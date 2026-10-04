# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Detail page for one project. All logic is shared; this only names the slug."""

import frappe

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import detail_context, record_route
from a3_sola.www.a3solaportal.project_overview import project_overview

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("projects", name) if name else "/a3solaportal/projects")
	detail_context(context, "projects", name)
	# A lead switcher, four boxes and the task table are the whole page.
	context.overview = project_overview(context.record)
	context.top_template = "templates/includes/portal_project_overview.html"
	context.hide_record_body = True
	# The project is worked from here; amending it is a desk task, not a button on this page.
	context.hide_desk_amend = True
	context.main_wide = True
	return context
