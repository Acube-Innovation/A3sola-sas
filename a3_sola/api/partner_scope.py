# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a partner - someone outside the company - may see: his own records, and nothing else.

Two partners log in to the portal:

- a **dealer** (Solar Dealer) brings customers in. He sees the leads he brought (Lead's Dealer)
  and everything raised for them: the customer, survey, estimate, eligibility check, proposal,
  quotation, and the project, to read;
- a **contractor** (Solar Contractor Partner) installs. He sees the projects whose structure or
  electrical contractor is his Solar Contractor record (its Portal User), with their tasks and
  work orders.

The doctype permissions say what a partner may do; this says to which records. Staff are never
narrowed here: a user who holds any role besides a partner role is treated as staff. Combined
with the company check in api/permissions, and bound to Lead, Customer and Quotation - which
carry no company scoping - by the registry.
"""

import frappe
from frappe import _

DEALER = "Solar Dealer"
CONTRACTOR = "Solar Contractor Partner"
PARTNER_ROLES = (DEALER, CONTRACTOR)
#: Roles every user holds; they do not make anyone staff.
AUTOMATIC_ROLES = {"All", "Guest", "Desk User"}


def partner_kind(user=None):
	"""'dealer', 'contractor', or None for staff and guests."""
	user = user or frappe.session.user
	if user in ("Administrator", "Guest"):
		return None
	roles = set(frappe.get_roles(user)) - AUTOMATIC_ROLES
	if not roles or not roles <= set(PARTNER_ROLES):
		return None
	return "dealer" if DEALER in roles else "contractor"


def is_partner(user=None):
	return bool(partner_kind(user))


def _dealer_sets(u):
	leads = f"select `name` from `tabLead` where `a3s_dealer` = {u}"
	consumers = f"select `name` from `tabSolar Consumer` where `dealer` = {u} or `lead` in ({leads})"
	customers = (f"select `customer` from `tabSolar Consumer` where ifnull(`customer`, '') != '' "
		f"and (`dealer` = {u} or `lead` in ({leads}))")
	projects = f"select `name` from `tabSolar Installation` where `lead` in ({leads}) or `solar_consumer` in ({consumers})"
	return leads, consumers, customers, projects


def _contractor_sets(u):
	mine = f"select `name` from `tabSolar Contractor` where `user` = {u}"
	projects = (f"select `name` from `tabSolar Installation` where `structure_contractor` in ({mine}) "
		f"or `electrical_contractor` in ({mine})")
	return mine, projects


def conditions(user, doctype):
	"""The SQL a partner's reads of `doctype` are narrowed by; "" when not narrowed."""
	kind = partner_kind(user)
	if not kind:
		return ""
	u = frappe.db.escape(user)
	t = f"`tab{doctype}`"
	if kind == "dealer":
		leads, consumers, customers, projects = _dealer_sets(u)
		by_sale = f"{t}.`lead` in ({leads}) or {t}.`solar_consumer` in ({consumers})"
		where = {
			"Lead": f"{t}.`a3s_dealer` = {u}",
			"Solar Consumer": f"{t}.`dealer` = {u} or {t}.`lead` in ({leads})",
			"Site Survey": by_sale,
			"Solar Design Estimate": by_sale,
			"Subsidy Eligibility Check": by_sale,
			"Solar Proposal": by_sale,
			"Solar Installation": by_sale,
			"Customer": f"{t}.`name` in ({customers}) or {t}.`lead_name` in ({leads})",
			"Quotation": f"{t}.`party_name` in ({leads}) or {t}.`party_name` in ({customers})",
			"Installation Task": f"{t}.`solar_installation` in ({projects})",
			"Installation Work Order": f"{t}.`solar_installation` in ({projects})",
		}.get(doctype)
	else:
		mine, projects = _contractor_sets(u)
		where = {
			"Solar Installation": f"{t}.`name` in ({projects})",
			"Installation Task": f"{t}.`solar_installation` in ({projects})",
			"Installation Work Order": f"{t}.`solar_installation` in ({projects}) or {t}.`solar_contractor` in ({mine})",
			"Solar Consumer": f"{t}.`name` in (select `solar_consumer` from `tabSolar Installation` where `name` in ({projects}))",
			"Solar Contractor": f"{t}.`user` = {u}",
		}.get(doctype)
	if not where:
		return ""
	# What he made himself is his too - a record saved before its links were filled.
	return f"({where} or {t}.`owner` = {u})"


def query_conditions(user=None, doctype=None, **kwargs):
	"""permission_query_conditions for doctypes with no company scoping (Lead, Customer, Quotation)."""
	return conditions(user or frappe.session.user, doctype) if doctype else ""


def has_permission(doc=None, ptype=None, user=None, **kwargs):
	"""A partner opens only the records `conditions` gives him; a new one he may make."""
	if doc is None:
		return True
	user = user or frappe.session.user
	where = conditions(user, doc.doctype)
	if not where:
		return True
	if doc.is_new() or not frappe.db.exists(doc.doctype, doc.name):
		return True
	return bool(frappe.db.sql(f"select 1 from `tab{doc.doctype}` where `name` = %s and {where}", doc.name))


#: Task pages a partner opens without being given the task: a contractor works the design
#: freezes and the serial numbers, a dealer reads the design freezes.
CONTRACTOR_TASKS = ("DSGN", "SDSGN", "SERIAL")
DEALER_TASKS = ("DSGN", "SDSGN")


def may_open_task(installation, code, user=None):
	"""Whether a partner may open a project's task page: his own task pages, or - a contractor -
	a task given to him. Staff always may."""
	user = user or frappe.session.user
	kind = partner_kind(user)
	if not kind:
		return True
	if code in (CONTRACTOR_TASKS if kind == "contractor" else DEALER_TASKS):
		return True
	if kind != "contractor":
		return False
	given = frappe.get_all("Installation Task Assignee", filters={"parent": installation, "stage_code": code}, pluck="user")
	row = frappe.db.get_value("Installation Stage Log", {"parent": installation, "parenttype": "Solar Installation",
		"stage_code": code}, "assigned_to")
	return user in given or user == row


def refuse_partners(what=None):
	"""Stop a partner at a page or call that is the company's own business - supplier bills,
	payments, costs, reimbursements."""
	if is_partner():
		frappe.throw(_("{0} is not available to partners.").format(what or _("This page")), frappe.PermissionError,
			title=_("Not Permitted"))


def stamp_dealer(doc, method=None):
	"""A lead or customer a dealer creates is his; a customer made from a dealer's lead is the
	dealer's too."""
	field = "a3s_dealer" if doc.doctype == "Lead" else "dealer"
	if doc.get(field):
		return
	if doc.doctype != "Lead" and doc.get("lead"):
		dealer = frappe.db.get_value("Lead", doc.lead, "a3s_dealer")
		if dealer:
			doc.set(field, dealer)
			return
	if partner_kind() == "dealer":
		doc.set(field, frappe.session.user)


def contractor_user(inst, role="electrical"):
	"""The portal user of a project's contractor (the project or its name), where he has one."""
	field = f"{role}_contractor"
	contractor = inst.get(field) if hasattr(inst, "get") else frappe.db.get_value("Solar Installation", inst, field)
	return frappe.db.get_value("Solar Contractor", contractor, "user") if contractor else None
