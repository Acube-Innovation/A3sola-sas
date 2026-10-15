# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task on the project board, opened: straight on to where it is carried out.

The task's document when it has one, else the form that creates it, filled in for this job
and task - `tasks.open_task` decides, as it does for the desk's Task button. The page itself
is only shown when there is nowhere to go.
"""

from urllib.parse import urlencode

import frappe

from a3_sola.api import tasks
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import SLUG_OF_DOCTYPE, desk_route, record_route

no_cache = 1

#: ERPNext forms with item tables the portal's create form cannot fill: created in the desk.
DESK_CREATE = {"Purchase Order", "Delivery Note"}


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	code = (frappe.form_dict.get("task") or "").strip()
	project = record_route("projects", name)
	require_login(f"{project}/tasks/{code}")
	try:
		target = tasks.open_task(name, code, create_draft=0)
	except frappe.ValidationError as e:
		return _nowhere(context, name, project, frappe.utils.strip_html(str(e)))

	frappe.local.flags.redirect_location = task_target(name, code, target) or project
	raise frappe.Redirect(302)


def task_target(installation, code, target):
	"""The URL a task opens at, from what `open_task` returned, or None for nothing to open."""
	doctype, docname, options = target.get("doctype"), target.get("name"), target.get("route_options")
	if docname:
		if doctype in SLUG_OF_DOCTYPE:
			return record_route(SLUG_OF_DOCTYPE[doctype], docname)
		return desk_route(doctype, docname)
	if not options:
		return None
	if doctype in SLUG_OF_DOCTYPE and doctype not in DESK_CREATE:
		query = {"source_dt": "Solar Installation", "source": installation, "task": code}
		return f"/a3solaportal/{SLUG_OF_DOCTYPE[doctype]}/new?{urlencode(query)}"
	options = {k: v for k, v in options.items() if v not in (None, "")}
	return "/app/{0}/new?{1}".format(frappe.scrub(doctype).replace("_", "-"), urlencode(options))


def _nowhere(context, name, project, message):
	fill_shell(
		context,
		active_route="/a3solaportal/projects",
		page_title="Task",
		crumbs=[
			{"label": "Home", "href": "/a3solaportal/dashboard"},
			{"label": "Project", "href": "/a3solaportal/projects"},
			{"label": name, "href": project},
			{"label": "Task"},
		],
	)
	context.message = message
	context.project_route = project
	return context
