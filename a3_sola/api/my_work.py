# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a person has to do, for their dashboard: Pending (late, or with no date), Today and
the next seven days.

Four kinds of work: the project tasks they are on (a job's task rows - the source of truth,
kept up to date as a task starts, moves or closes), the leads they follow up, what has been
assigned to them on a record (open ToDos), and the service tickets they hold. A manager may
also see the whole team's.
"""

from datetime import timedelta

import frappe
from frappe.utils import getdate, strip_html, today

#: How far ahead "Upcoming" looks.
UPCOMING_DAYS = 7
#: Rows read from each kind of work.
LIMIT = 200
MANAGER_ROLES = ("System Manager", "Solar Project Manager", "Solar Operations Manager", "Solar CRM Manager",
	"Solar Sales Manager")
CLOSED_TASK = ("Completed", "Skipped")
CLOSED_LEAD = ("Converted", "Do Not Contact", "Lost Quotation")
CLOSED_TICKET = ("Resolved", "Closed")
#: Kinds of work, as the dashboard names them.
TASK, FOLLOW_UP, ASSIGNMENT, TICKET = "Task", "Follow-up", "Assignment", "Ticket"


def is_manager(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & set(MANAGER_ROLES))


def items(user, team=False):
	"""Every open piece of work of `user` - or, for the team, of everyone."""
	return project_tasks(user, team) + lead_follow_ups(user, team) + assignments(user, team) + tickets(user, team)


def _route(slug, name):
	from a3_sola.www.a3solaportal.collections import record_route

	return record_route(slug, name)


def project_tasks(user, team=False):
	"""Open task rows of open jobs the person is on - as any of a task's people, not only the
	first. Due when the task is due, else when the plan has it end."""
	people = frappe.db.sql("""select parent, stage_code, user from `tabInstallation Task Assignee`
		where parenttype = 'Solar Installation'""", as_dict=True)
	by_task = {}
	for p in people:
		by_task.setdefault((p.parent, p.stage_code), []).append(p.user)
	rows = frappe.db.sql("""select s.parent, s.stage_code, s.stage_name, s.status, s.due_date, s.planned_date,
			s.assigned_to, i.consumer_name
		from `tabInstallation Stage Log` s join `tabSolar Installation` i on i.name = s.parent
		where s.parenttype = 'Solar Installation' and i.docstatus < 2 and i.status not in ('Closed', 'Cancelled')
			and s.status not in %(closed)s
		order by coalesce(s.due_date, s.planned_date), s.idx""", {"closed": CLOSED_TASK}, as_dict=True)
	out = []
	for r in rows:
		on_it = by_task.get((r.parent, r.stage_code)) or ([r.assigned_to] if r.assigned_to else [])
		if not on_it or (not team and user not in on_it):
			continue
		out.append({
			"kind": TASK, "title": r.stage_name, "context": " · ".join(x for x in (r.consumer_name, r.parent) if x),
			"due": getdate(r.due_date or r.planned_date) if (r.due_date or r.planned_date) else None,
			"status": r.status, "url": "{0}/tasks/{1}".format(_route("projects", r.parent), frappe.utils.quote(r.stage_code)),
			"people": on_it,
		})
		if len(out) >= LIMIT:
			break
	return out


def lead_follow_ups(user, team=False):
	"""Leads the person owns whose next follow-up is set, while the lead is still open."""
	filters = {"next_followup_date": ["is", "set"], "status": ["not in", CLOSED_LEAD]}
	rows = frappe.get_all("Lead", filters=filters, fields=["name", "lead_name", "next_followup_date", "status",
		"lead_owner", "owner", "mobile_no"], order_by="next_followup_date asc", limit_page_length=LIMIT * 2)
	out = []
	for r in rows:
		owner = r.lead_owner or r.owner
		if not team and owner != user:
			continue
		out.append({
			"kind": FOLLOW_UP, "title": "Follow up: {0}".format(r.lead_name or r.name),
			"context": " · ".join(x for x in (r.status, r.mobile_no) if x), "due": getdate(r.next_followup_date),
			"status": r.status, "url": "/a3solaportal/leads/{0}".format(frappe.utils.quote(r.name)), "people": [owner],
		})
	return out[:LIMIT]


def _is_duplicate(todo):
	"""A ToDo that repeats work listed on its own: a project task's (made as the task starts,
	"[CODE] name" on the job), or the daily digest of leads to follow up."""
	if todo.reference_type == "Solar Installation" and (todo.description or "").lstrip().startswith("["):
		return True
	return todo.reference_type == "Lead" and "due for follow-up" in (todo.description or "")


def assignments(user, team=False):
	"""Open ToDos: a survey to do, a record handed to the person, an escalation, a snag."""
	from a3_sola.www.a3solaportal.collections import SLUG_OF_DOCTYPE

	filters = {"status": "Open"}
	if not team:
		filters["allocated_to"] = user
	rows = frappe.get_all("ToDo", filters=filters, fields=["name", "description", "date", "reference_type",
		"reference_name", "allocated_to", "priority"], order_by="date asc", limit_page_length=LIMIT * 2)
	out = []
	for r in rows:
		if _is_duplicate(r):
			continue
		if r.reference_type and r.reference_name:
			slug = "leads" if r.reference_type == "Lead" else SLUG_OF_DOCTYPE.get(r.reference_type)
			url = _route(slug, r.reference_name) if slug else "/app/{0}/{1}".format(
				frappe.scrub(r.reference_type).replace("_", "-"), frappe.utils.quote(r.reference_name))
		else:
			url = "/app/todo/{0}".format(r.name)
		text = " ".join(strip_html(r.description or "").split())
		out.append({
			"kind": ASSIGNMENT, "title": (text[:110] + "…") if len(text) > 110 else (text or r.reference_name or "To do"),
			"context": " · ".join(x for x in (r.reference_type, r.reference_name) if x), "due": getdate(r.date) if r.date else None,
			"status": r.priority, "url": url, "people": [r.allocated_to] if r.allocated_to else [],
		})
	return out[:LIMIT]


def tickets(user, team=False):
	"""Open service tickets the person holds: due to be answered, then to be resolved."""
	if not frappe.db.exists("DocType", "Service Ticket"):
		return []
	filters = {"docstatus": ["<", 2], "status": ["not in", CLOSED_TICKET], "assigned_to": ["is", "set"]}
	if not team:
		filters["assigned_to"] = user
	rows = frappe.get_all("Service Ticket", filters=filters, fields=["name", "customer", "category", "severity",
		"status", "response_due_by", "resolution_due_by", "first_response_on", "assigned_to"],
		order_by="resolution_due_by asc", limit_page_length=LIMIT)
	out = []
	for r in rows:
		due = r.resolution_due_by if r.first_response_on else (r.response_due_by or r.resolution_due_by)
		out.append({
			"kind": TICKET, "title": "{0}{1}".format(r.category or "Service ticket", " ({0})".format(r.severity) if r.severity else ""),
			"context": " · ".join(x for x in (r.customer, r.name, r.status) if x), "due": getdate(due) if due else None,
			"status": r.status, "url": _route("service-tickets", r.name), "people": [r.assigned_to],
		})
	return out


def buckets(work, on=None):
	"""Work as the dashboard shows it: Pending (late, oldest first, then undated), Today, the next
	seven days, and how many fall later."""
	on = getdate(on or today())
	horizon = on + timedelta(days=UPCOMING_DAYS)
	late, undated, now, upcoming, later = [], [], [], [], 0
	for w in work:
		due = w.get("due")
		if due is None:
			undated.append(w)
		elif due < on:
			w["late_days"] = (on - due).days
			late.append(w)
		elif due == on:
			now.append(w)
		elif due <= horizon:
			upcoming.append(w)
		else:
			later += 1
	late.sort(key=lambda w: w["due"])
	upcoming.sort(key=lambda w: w["due"])
	return {"pending": late + undated, "today": now, "upcoming": upcoming, "later": later,
		"counts": {"overdue": len(late), "today": len(now), "upcoming": len(upcoming), "undated": len(undated)}}


def people_names(work):
	"""Each item's people by full name, for the team's view."""
	users = {u for w in work for u in w.get("people") or []}
	names = dict(frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
		as_list=True)) if users else {}
	for w in work:
		w["people_names"] = ", ".join(names.get(u) or u for u in w.get("people") or [])
	return work
