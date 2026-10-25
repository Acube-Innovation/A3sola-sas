# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Who carries out a customer's site survey: a to-do on the customer (a ToDo, as the desk's
Assign makes), given from its page's Next steps. Only the person it is assigned to may create
the survey - and the survey, once created, closes the to-do and names them its surveyor.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

CONSUMER = "Solar Consumer"
#: How a to-do on a customer says it is the site survey.
MARKER = "Site survey"


def _open(consumer):
	"""The customer's open site-survey to-do (the newest), or None."""
	rows = frappe.get_all("ToDo", filters={"reference_type": CONSUMER, "reference_name": consumer, "status": "Open",
		"description": ["like", f"%{MARKER}%"]}, fields=["name", "allocated_to", "date", "assigned_by", "description"],
		order_by="creation desc", limit=1)
	return rows[0] if rows else None


def assignee(consumer):
	"""Who the customer's site survey is assigned to, or None."""
	row = _open(consumer)
	return row.allocated_to if row else None


def _full_name(user):
	return (frappe.db.get_value("User", user, "full_name") or user) if user else ""


def surveyors():
	"""Who a site survey can be assigned to: the enabled users who may create one."""
	roles = set(frappe.get_all("DocPerm", filters={"parent": "Site Survey", "create": 1}, pluck="role")) | set(
		frappe.get_all("Custom DocPerm", filters={"parent": "Site Survey", "create": 1}, pluck="role"))
	users = set(frappe.get_all("Has Role", filters={"parenttype": "User", "role": ["in", list(roles) or [""]]}, pluck="parent"))
	rows = frappe.get_all("User", filters={"name": ["in", list(users - {"Administrator", "Guest"}) or [""]], "enabled": 1,
		"user_type": "System User"}, fields=["name", "full_name"], order_by="full_name asc")
	return [{"value": r.name, "label": r.full_name or r.name} for r in rows]


def state(doc):
	"""The page's survey assignment: who has it and when it is due, whether it is this user,
	and whether this user may (re)assign it. None once the customer has a survey."""
	from a3_sola.api import portal_chain

	step = next((s for s in portal_chain.CHAIN.get(CONSUMER, []) if s.get("key") == "survey"), None)
	if step and portal_chain.find_target(step, doc):
		return None
	row = _open(doc.name)
	return frappe._dict({
		"assignee": row.allocated_to if row else None,
		"assignee_name": _full_name(row.allocated_to) if row else "",
		"due": frappe.utils.formatdate(row.date, "d MMM yyyy") if row and row.date else "",
		"assigned_by": _full_name(row.assigned_by) if row else "",
		"is_me": bool(row) and row.allocated_to == frappe.session.user,
		"can_assign": bool(doc.has_permission("write")),
	})


@frappe.whitelist()
def candidates(consumer=None):
	"""The people the survey can be assigned to, for the Assign dialog."""
	frappe.get_doc(CONSUMER, consumer).check_permission("write")
	return {"users": surveyors(), "me": frappe.session.user}


@frappe.whitelist(methods=["POST"])
def assign(consumer=None, user=None, complete_by=None, comment=None):
	"""Assign the customer's site survey to `user` (by `complete_by`), replacing any earlier
	assignment - a to-do on the customer, in their list."""
	from frappe.desk.form import assign_to

	doc = frappe.get_doc(CONSUMER, consumer)
	doc.check_permission("write")
	if user not in {u["value"] for u in surveyors()}:
		frappe.throw(_("{0} cannot carry out a site survey.").format(user or _("Nobody")), frappe.ValidationError)
	if complete_by and getdate(complete_by) < getdate(today()):
		frappe.throw(_("The survey cannot be due in the past."))
	current = _open(doc.name)
	if current and current.allocated_to == user:
		return state(doc)
	if current:
		# Reassigned: the earlier person's to-do is cancelled, as the desk's remove does.
		frappe.db.set_value("ToDo", current.name, "status", "Cancelled")
	description = _("{0} for {1}").format(MARKER, doc.consumer_name or doc.name)
	if (comment or "").strip():
		description += " - " + comment.strip()
	assign_to.add({"assign_to": [user], "doctype": CONSUMER, "name": doc.name, "description": description,
		"date": complete_by or None, "priority": "Medium"})
	return state(doc)


def check_create(survey):
	"""A site survey for a customer is created by the person it is assigned to (Site Survey
	before_insert). Records made by the system - starter data, imports, Administrator - are not
	held to it."""
	if not survey.get("solar_consumer") or survey.flags.ignore_permissions or frappe.session.user == "Administrator":
		return
	if frappe.flags.in_import or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	who = assignee(survey.solar_consumer)
	if not who:
		frappe.throw(_("Assign the site survey for {0} first: only the person it is assigned to can create it.").format(
			survey.solar_consumer), title=_("Site Survey Not Assigned"))
	if who != frappe.session.user:
		frappe.throw(_("The site survey for {0} is assigned to {1}: only they can create it.").format(
			survey.solar_consumer, _full_name(who)), title=_("Assigned to Someone Else"))
	if not survey.get("surveyor"):
		survey.surveyor = who


def close_on_create(survey):
	"""The survey is made: its to-do is done (Site Survey after_insert)."""
	if not survey.get("solar_consumer"):
		return
	row = _open(survey.solar_consumer)
	if row:
		frappe.db.set_value("ToDo", row.name, "status", "Closed")
