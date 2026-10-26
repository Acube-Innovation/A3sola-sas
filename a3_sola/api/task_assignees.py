# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Who a project's tasks are assigned to - any number of people per task.

Each task on the template names a default position (`default_assignee`: Project Engineer,
Project Manager, Sales Co-ordinator, Lead Owner, Accounts, Contractor). On a project that
position is a person: the job's own Project Manager, Project Engineer (`site_engineer`) and
Sales Co-ordinator fields, its lead's owner, and everyone in Accounts. A contractor has no
login, so a contractor's task goes to the Project Engineer, with the contractor named on
the card.

The people are the job's `task_assignees` rows (task code, user); the task row's own
`assigned_to` is the first of them, which is what the rest of the app reads.
"""

import json

import frappe
from frappe import _

from a3_sola.api.stages import _get_stage

PROJECT_ENGINEER = "Project Engineer"
PROJECT_MANAGER = "Project Manager"
SALES_COORDINATOR = "Sales Co-ordinator"
LEAD_OWNER = "Lead Owner"
ACCOUNTS = "Accounts"
CONTRACTOR = "Contractor"

#: The job's field holding each position's person.
POSITION_FIELDS = {
	PROJECT_ENGINEER: "site_engineer",
	PROJECT_MANAGER: "project_manager",
	SALES_COORDINATOR: "sales_coordinator",
}
#: The role a job's position is prefilled from, when exactly one person holds it.
POSITION_ROLES = {"site_engineer": "Solar Site Engineer", "sales_coordinator": "Solar Sales Coordinator"}
ACCOUNTS_ROLE = "Solar Accounts Executive"
CLOSED = ("Completed", "Skipped")


def role_holders(role):
	"""The enabled people who hold `role` as their job - not Administrator, and not a system
	manager, who holds every role without doing the work."""
	users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	if not users:
		return []
	admins = set(frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent"))
	enabled = set(frappe.get_all("User", filters={"name": ["in", users], "enabled": 1, "user_type": "System User"}, pluck="name"))
	return sorted(u for u in users if u in enabled and u not in admins and u not in ("Administrator", "Guest"))


def prefill_people(inst):
	"""Fill a job's blank Project Engineer and Sales Co-ordinator from their role, when one
	person holds it; more than one is a choice for a person to make."""
	for field, role in POSITION_ROLES.items():
		if not inst.get(field):
			holders = role_holders(role)
			if len(holders) == 1:
				inst.set(field, holders[0])


def resolve(inst, position):
	"""The people a position means on this job."""
	if position == CONTRACTOR:
		position = PROJECT_ENGINEER
	field = POSITION_FIELDS.get(position)
	if field:
		return [inst.get(field)] if inst.get(field) else []
	if position == LEAD_OWNER:
		owner = frappe.db.get_value("Lead", inst.lead, "lead_owner") if inst.get("lead") else None
		return [owner] if owner else []
	if position == ACCOUNTS:
		return role_holders(ACCOUNTS_ROLE)
	return []


def people(inst, code):
	return [r.user for r in inst.get("task_assignees") or [] if r.stage_code == code]


def put(inst, code, users):
	"""Make `users` the task's assignees, in order; its row's `assigned_to` is the first."""
	seen, wanted = set(), []
	for user in users:
		if user and user not in seen:
			seen.add(user)
			wanted.append(user)
	inst.set("task_assignees", [r for r in inst.get("task_assignees") or [] if r.stage_code != code])
	for user in wanted:
		inst.append("task_assignees", {"stage_code": code, "user": user})
	row = next((r for r in inst.stages if r.stage_code == code), None)
	if row:
		row.assigned_to = wanted[0] if wanted else None


def add(inst, code, user):
	"""One more person on the task, keeping those already there."""
	if user and user not in people(inst, code):
		put(inst, code, people(inst, code) + [user])


def apply_defaults(inst):
	"""Give every task with nobody on it its default people. A task already assigned - by
	hand or by its document - is left as it is."""
	if not inst.get("stages"):
		return
	defaults, named = _template_defaults(inst), template_users(inst)
	for row in inst.stages:
		row.default_assignee = row.get("default_assignee") or defaults.get(row.stage_code)
		if people(inst, row.stage_code):
			continue
		users = default_people(inst, row, named)
		if not users and row.assigned_to:
			users = [row.assigned_to]
		if users:
			put(inst, row.stage_code, users)


def follow_people(inst, before):
	"""A position on the job changed hands: its open tasks go to the new person in place of
	the old, and anyone added beside them stays."""
	if not before:
		return
	for position, field in POSITION_FIELDS.items():
		old, new = before.get(field), inst.get(field)
		if old == new:
			continue
		follows = {position, CONTRACTOR} if position == PROJECT_ENGINEER else {position}
		for row in inst.stages:
			if row.get("default_assignee") not in follows or row.status in CLOSED:
				continue
			current = people(inst, row.stage_code)
			if old in current:
				current = [new if u == old else u for u in current] if new else [u for u in current if u != old]
			elif new and not current:
				current = [new]
			else:
				continue
			put(inst, row.stage_code, current)


def default_people(inst, row, named=None):
	"""Who a task goes to by default: the person the template names for it (Assign to), else
	whoever holds its position on the job."""
	user = (named if named is not None else template_users(inst)).get(row.stage_code)
	if user and frappe.db.get_value("User", user, "enabled"):
		return [user]
	return resolve(inst, row.default_assignee) if row.get("default_assignee") else []


def template_users(inst):
	"""{task code: user} - the person the job's template names for each task, if any."""
	if not inst.get("stage_template"):
		return {}
	return dict(frappe.db.sql(
		"""select stage_code, default_user from `tabInstallation Stage Template Detail`
		where parent = %s and parenttype = 'Installation Stage Template' and ifnull(default_user, '') != ''""",
		inst.stage_template,
	))


def _template_defaults(inst):
	if not inst.get("stage_template"):
		return {}
	# A plain query: get_all drops a column named `default_assignee` from its field list.
	return dict(frappe.db.sql(
		"""select stage_code, default_assignee from `tabInstallation Stage Template Detail`
		where parent = %s and parenttype = 'Installation Stage Template'""",
		inst.stage_template,
	))


# ------------------------------------------------------------------ the portal's calls
@frappe.whitelist()
def candidates(installation):
	"""Who a task can be assigned to: the enabled people of the office, as name and id."""
	frappe.get_doc("Solar Installation", installation).check_permission("read")
	return frappe.get_all(
		"User", filters={"enabled": 1, "user_type": "System User", "name": ["not in", ("Administrator", "Guest")]},
		fields=["name", "full_name"], order_by="full_name asc",
	)


@frappe.whitelist(methods=["POST"])
def set_task_assignees(installation, task_code, users=None):
	"""Assign the task to exactly `users` (a list, or its JSON) - added, removed, reordered."""
	inst = frappe.get_doc("Solar Installation", installation, for_update=True)
	inst.check_permission("write")
	row = _get_stage(inst, task_code)
	if isinstance(users, str):
		users = json.loads(users or "[]")
	users = [u for u in (users or []) if u]
	unknown = [u for u in users if not frappe.db.exists("User", {"name": u, "enabled": 1})]
	if unknown:
		frappe.throw(_("Not a user who can be assigned: {0}").format(", ".join(unknown)), frappe.ValidationError)
	before = people(inst, task_code)
	put(inst, task_code, users)
	# The task's document names the lead person too.
	if row.task_document and frappe.get_meta(row.task_doctype).has_field("assigned_to"):
		frappe.db.set_value(row.task_doctype, row.task_document, "assigned_to", users[0] if users else None,
			update_modified=False)
	names = dict(frappe.get_all("User", filters={"name": ["in", users or [""]]}, fields=["name", "full_name"], as_list=True))
	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	if before != users:
		inst.add_comment("Info", _("Task {0} assigned to {1}").format(
			row.stage_name, ", ".join(names.get(u) or u for u in users) or _("nobody")))
	return {"assignees": [{"user": u, "full_name": names.get(u) or u} for u in users]}
