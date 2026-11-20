# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Administration > Task Assignees: who each project task goes to by default, and its SLA.

Every task of the project task template (stages.resolve_template) has
- a default position (Project Engineer, Project Manager, Sales Co-ordinator, Lead Owner,
  Accounts, Contractor), which on a project is that project's own person (task_assignees);
- optionally a named person, who takes the task on every project in place of the position;
- when it starts (Starts When: in order from the project start, the first payment - or the
  order on a self-funded job - 50% payment, or after another task), from which its SLA days
  count;
- its SLA days, from which the project's planned dates are laid (stages.plan_dates).

Saving changes the template's rows. A new project takes the people and SLAs as they are; a
running project takes the new SLAs, and its dates move, on its next save
(stages.sync_from_template), while a task already assigned on it keeps its people.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from a3_sola.api.portal_users import require_admin

ROUTE = "/a3solaportal/task-assignees"
TEMPLATE = "Installation Stage Template"
DETAIL = "Installation Stage Template Detail"
#: Starts When as the page's list says it, shorter than the stored choice.
TRIGGER_LABELS = {
	"In order from the project start": "In order (project start)",
	"First payment": "First payment",
	"First payment, or with the order if self-funded": "First payment, or order if self-funded",
	"50% payment": "50% payment",
	"After another task": "After another task",
}


def template_name():
	from a3_sola.api.stages import resolve_template

	try:
		return resolve_template()
	except frappe.ValidationError:
		return None


def positions():
	"""The positions a task can default to, as the template's field offers them."""
	options = frappe.get_meta(DETAIL).get_field("default_assignee").options or ""
	return [o for o in options.splitlines() if o.strip()]


def triggers():
	"""The Starts When choices, as the template's field offers them."""
	options = frappe.get_meta(DETAIL).get_field("start_trigger").options or ""
	return [o for o in options.splitlines() if o.strip()]


def people():
	"""The office's enabled people a task can be named to."""
	return frappe.get_all(
		"User", filters={"enabled": 1, "user_type": "System User", "name": ["not in", ("Administrator", "Guest")]},
		fields=["name", "full_name"], order_by="full_name asc",
	)


def tasks(name=None):
	"""The template's tasks in their order, each with its position, person and SLA."""
	name = name or template_name()
	if not name:
		return []
	# A plain query: get_all drops a column named `default_assignee` from its field list.
	return frappe.db.sql(
		"""select name, stage_code, stage_name, owner_type, default_assignee, default_user, sla_days,
			start_trigger, start_after_task, display_order, idx
		from `tabInstallation Stage Template Detail`
		where parent = %s and parenttype = %s order by display_order, idx""",
		(name, TEMPLATE), as_dict=True,
	)


def page_data():
	name = template_name()
	return {
		"task_template": name,
		"template_title": frappe.db.get_value(TEMPLATE, name, "template_name") if name else "",
		"tasks": tasks(name),
		"positions": positions(),
		"triggers": triggers(),
		"people": people(),
		"projects": frappe.db.count("Solar Installation", {"docstatus": ["<", 2], "stage_template": name}) if name else 0,
	}


@frappe.whitelist(methods=["POST"])
def save(rows):
	"""Save the tasks' positions, people and SLA days: [{name, default_assignee, default_user,
	sla_days}], `name` being the template row's. Admins only."""
	require_admin()
	name = template_name()
	if not name:
		frappe.throw(_("There is no project task template to change."), title=_("No Task Template"))
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	wanted = {r.get("name"): r for r in rows or [] if r.get("name")}
	valid_positions = set(positions())
	enabled = {u.name for u in people()}

	from a3_sola.api.stages import AFTER_TASK

	valid_triggers = set(triggers())
	doc = frappe.get_doc(TEMPLATE, name)
	codes = {row.stage_code for row in doc.stages}
	changed = 0
	for row in doc.stages:
		values = wanted.get(row.name)
		if not values:
			continue
		position = (values.get("default_assignee") or "").strip()
		user = (values.get("default_user") or "").strip()
		sla = cint(values.get("sla_days"))
		if position and position not in valid_positions:
			frappe.throw(_("{0}: {1} is not a position.").format(row.stage_name, position), title=_("Unknown Position"))
		if user and user not in enabled:
			frappe.throw(_("{0}: {1} is not an active user.").format(row.stage_name, user), title=_("Unknown Person"))
		if sla < 0 or sla > 365:
			frappe.throw(_("{0}: SLA days must be between 0 and 365.").format(row.stage_name), title=_("SLA Days"))
		trigger = (values.get("start_trigger") or row.start_trigger or "").strip()
		after = (values.get("start_after_task") or "").strip() if trigger == AFTER_TASK else ""
		if trigger and trigger not in valid_triggers:
			frappe.throw(_("{0}: {1} is not a Starts When choice.").format(row.stage_name, trigger), title=_("Starts When"))
		if trigger == AFTER_TASK:
			if not after:
				frappe.throw(_("{0} starts after another task: choose which.").format(row.stage_name), title=_("Starts When"))
			if after == row.stage_code or after not in codes:
				frappe.throw(_("{0} cannot start after {1}.").format(row.stage_name, after), title=_("Starts When"))
		new = (position or None, user or None, sla, trigger or None, after or None)
		if (row.default_assignee or None, row.default_user or None, cint(row.sla_days),
				row.start_trigger or None, row.start_after_task or None) != new:
			row.default_assignee, row.default_user, row.sla_days, row.start_trigger, row.start_after_task = new
			changed += 1
	_refuse_loops(doc)
	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
	return {"changed": changed}


def _refuse_loops(doc):
	"""A task cannot, through the tasks it starts after, wait on itself: it would never start."""
	from a3_sola.api.stages import AFTER_TASK

	after = {r.stage_code: r.start_after_task for r in doc.stages if r.start_trigger == AFTER_TASK and r.start_after_task}
	names = {r.stage_code: r.stage_name for r in doc.stages}
	for code in after:
		seen, current = {code}, after.get(code)
		while current:
			if current in seen:
				frappe.throw(_("{0} would wait on itself through the tasks it starts after.").format(names.get(code, code)),
					title=_("Starts When"))
			seen.add(current)
			current = after.get(current)
