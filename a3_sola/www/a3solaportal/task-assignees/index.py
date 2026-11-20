# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Task Assignees page: an admin sets, for each project task, the position it goes to,
a person in place of the position, and its SLA days (api/task_defaults). Admins only."""

import frappe

from a3_sola.api import portal_users, task_defaults
from a3_sola.www.a3solaportal import fill_shell, require_login

no_cache = 1


def get_context(context):
	require_login(task_defaults.ROUTE)
	portal_users.require_admin()
	fill_shell(
		context,
		active_route=task_defaults.ROUTE,
		page_title="Task Assignees",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Task Assignees"}],
	)
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.update(task_defaults.page_data())
	context.trigger_labels = task_defaults.TRIGGER_LABELS
	return context
