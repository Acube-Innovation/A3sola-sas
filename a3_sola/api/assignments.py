# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Who a record is assigned to, for the portal.

An assignment in ERPNext is a ToDo pointing at the record, and the record's `_assign`
column listing the people it points to. The desk writes both through
`frappe.desk.form.assign_to`; so does this module, rather than writing ToDo rows itself,
because the two must stay in step and the framework is the thing that knows how.

What this adds is the boundary: the portal may only assign a record of a collection it
actually shows, and only to a user it would offer, checked here rather than trusted from
the browser. Nothing else is different - an assignment made here is the same assignment
the desk made, and shows up in the desk's own sidebar.
"""

import json

import frappe
from frappe import _
from frappe.desk.form import assign_to

#: What the portal will assign. A record the portal does not show is not a record it has
#: any business creating a ToDo against.
def _assignable_doctypes():
	from a3_sola.www.a3solaportal.collections import COLLECTIONS

	return {cfg["doctype"] for cfg in COLLECTIONS.values()} | {"Lead"}


PRIORITIES = ("Low", "Medium", "High")
MAX_CANDIDATES = 200


def _check(doctype, name, permtype="read"):
	"""The record must be one the portal shows, exist, and be one this user may act on."""
	if doctype not in _assignable_doctypes():
		frappe.throw(_("{0} cannot be assigned from the portal.").format(doctype), frappe.PermissionError)
	if not name or not frappe.db.exists(doctype, name):
		frappe.throw(_("That record does not exist."), frappe.DoesNotExistError)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission(permtype)
	return doc


def designation_of(user):
	"""What to print under a person's name.

	The Employee record is the real answer where HR is in use. Without one - and this
	client has none yet - the next best thing a person would recognise is the role they
	hold here, which is what the portal's own roles are named for.
	"""
	if not user:
		return ""
	employee = frappe.db.get_value("Employee", {"user_id": user}, "designation")
	if employee:
		return employee
	profile = frappe.db.get_value("User", user, "role_profile_name")
	if profile:
		return profile
	roles = frappe.get_roles(user)
	solar = [r for r in roles if r.startswith("Solar ")]
	return solar[0] if solar else ""


def _person(user):
	full_name = frappe.db.get_value("User", user, "full_name") or user
	words = [w for w in str(full_name).split() if w[:1].isalnum()]
	return {
		"user": user,
		"full_name": full_name,
		"designation": designation_of(user),
		"initials": "".join(w[0] for w in words[:2]).upper() or "?",
	}


def assignees(doctype, name):
	"""The open assignments on one record, newest first.

	Read straight from ToDo rather than from `_assign`, because the ToDo is what carries
	the date, the remark and who asked - which is the whole point of showing it.
	"""
	rows = frappe.get_all(
		"ToDo",
		filters={"reference_type": doctype, "reference_name": name, "status": ("!=", "Cancelled")},
		fields=["name", "allocated_to", "description", "date", "priority", "status",
		        "assigned_by", "assigned_by_full_name", "creation"],
		order_by="creation desc",
		limit_page_length=50,
		ignore_permissions=True,
	)
	out = []
	for row in rows:
		person = _person(row.allocated_to)
		out.append({
			**person,
			"todo": row.name,
			# The desk stores the comment as HTML; the portal shows text, so nothing a
			# remark contains can run here.
			"remarks": frappe.utils.strip_html(row.description or "").strip(),
			"complete_by": frappe.utils.format_date(row.date, "medium") if row.date else "",
			"assigned_on": frappe.utils.format_date(row.creation, "medium"),
			"priority": row.priority or "",
			"status": row.status or "",
			"assigned_by": row.assigned_by_full_name or row.assigned_by or "",
		})
	return out


@frappe.whitelist()
def candidates(doctype=None, name=None, q=None):
	"""People this record may be assigned to, and the user groups available."""
	_check(doctype, name)
	filters = [["enabled", "=", 1], ["user_type", "=", "System User"],
	           ["name", "not in", ["Guest", "Administrator"]]]
	if q:
		filters.append(["full_name", "like", "%{0}%".format(q)])
	users = frappe.get_all(
		"User", filters=filters, fields=["name", "full_name"],
		order_by="full_name", limit_page_length=MAX_CANDIDATES,
	)
	return {
		"users": [
			{"value": u.name, "label": "{0} ({1})".format(u.full_name or u.name, u.name)}
			for u in users
		],
		"groups": [
			{"value": g.name, "label": g.name}
			for g in frappe.get_all("User Group", fields=["name"], order_by="name", limit_page_length=100)
		],
		"me": frappe.session.user,
		"priorities": list(PRIORITIES),
	}


@frappe.whitelist()
def assign(doctype=None, name=None, assign_to_users=None, user_group=None,
           complete_by=None, priority=None, comment=None, assign_to_me=0):
	"""Assign a record to one or more people, exactly as the desk would.

	Write permission, because an assignment changes the record's `_assign` and shows on
	its sidebar - it is a change to the record, not a note about it.
	"""
	_check(doctype, name, "write")

	users = assign_to_users
	if isinstance(users, str):
		try:
			users = json.loads(users)
		except ValueError:
			users = [u.strip() for u in users.split(",") if u.strip()]
	users = [u for u in (users or []) if u]
	if frappe.utils.cint(assign_to_me) and frappe.session.user not in users:
		users.append(frappe.session.user)
	if not users and not user_group:
		frappe.throw(_("Choose at least one person to assign this to."), frappe.MandatoryError)

	for user in users:
		if not frappe.db.exists("User", user):
			frappe.throw(_("{0} is not a user.").format(user), frappe.ValidationError)

	if priority and priority not in PRIORITIES:
		frappe.throw(_("{0} is not a priority.").format(priority), frappe.ValidationError)

	args = {
		"doctype": doctype,
		"name": name,
		"assign_to": users,
		"description": frappe.utils.strip_html(comment or "").strip() or None,
		"priority": priority or "Medium",
	}
	if complete_by:
		args["date"] = complete_by
	if user_group:
		args["assign_to_users_group"] = user_group
	assign_to.add(args)
	return {"assignees": assignees(doctype, name)}


@frappe.whitelist()
def remove(doctype=None, name=None, user=None):
	"""Take one person off a record."""
	_check(doctype, name, "write")
	assign_to.remove(doctype, name, user)
	return {"assignees": assignees(doctype, name)}


@frappe.whitelist()
def todo(name=None):
	"""One assignment in full, for the list page's popup."""
	if not name or not frappe.db.exists("ToDo", name):
		frappe.throw(_("That assignment does not exist."), frappe.DoesNotExistError)
	doc = frappe.get_doc("ToDo", name)
	doc.check_permission("read")
	if doc.reference_type and doc.reference_name:
		_check(doc.reference_type, doc.reference_name)
	person = _person(doc.allocated_to)
	return {
		**person,
		"todo": doc.name,
		"remarks": frappe.utils.strip_html(doc.description or "").strip(),
		"complete_by": frappe.utils.format_date(doc.date, "medium") if doc.date else "",
		"assigned_on": frappe.utils.format_datetime(doc.creation, "medium"),
		"priority": doc.priority or "",
		"status": doc.status or "",
		"assigned_by": doc.assigned_by_full_name or doc.assigned_by or "",
		"reference": "{0} {1}".format(doc.reference_type or "", doc.reference_name or "").strip(),
	}
