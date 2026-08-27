# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The shared multi-tenant permission implementation.

ONE implementation, used by every module through the registry. Phases 2 to 7 register
their doctypes here and never write their own filter logic - that is the concrete benefit
of the single-app design, so take it.

Two layers, because either alone is insufficient:
  * permission_query_conditions filters list views, reports and link searches.
  * has_permission denies opening a single document by its direct URL.
"""

import frappe
from frappe import _


def get_permitted_companies(user=None):
	"""Companies the user may see.

	None means unrestricted (no User Permission applied) - Frappe's own convention.
	"""
	user = user or frappe.session.user
	if user == "Administrator":
		return None

	permissions = frappe.defaults.get_user_permissions(user) or {}
	entry = permissions.get("Company")
	if not entry:
		return None
	return [row.get("doc") for row in entry if row.get("doc")]


def build_query_conditions(user, doctype):
	"""SQL fragment restricting a doctype to the user's permitted companies."""
	companies = get_permitted_companies(user)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	table = f"`tab{doctype}`"
	quoted = ", ".join(frappe.db.escape(c) for c in companies)
	return f"({table}.`company` in ({quoted}) or {table}.`company` is null)"


def query_conditions(user=None, doctype=None, **kwargs):
	"""permission_query_conditions hook.

	One module-level function serves every registered doctype: Frappe passes the doctype
	on each call, so there is no need for a closure per doctype — and the hooks dict is
	pickled into the cache, so a closure could not live there anyway.
	"""
	if not doctype:
		return ""
	return build_query_conditions(user or frappe.session.user, doctype)


def has_company_permission(doc=None, ptype=None, user=None, **kwargs):
	"""Deny row-level access to a document whose company the user is not permitted on.

	This is the layer that stops a Company B document being opened by its direct URL, which
	`query_conditions` alone does not cover.
	"""
	if doc is None:
		return None
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	company = getattr(doc, "company", None)
	if not company:
		return True
	companies = get_permitted_companies(user)
	if companies is None:
		return True
	return company in companies


def assert_same_company(doc, links):
	"""Assert every linked document belongs to the same company as `doc`.

	`links` is an iterable of (fieldname, doctype). A Site Survey in Company A must never
	link a Solar Consumer in Company B, and the error must name the offending link rather
	than failing abstractly.
	"""
	company = getattr(doc, "company", None)
	if not company:
		return

	for fieldname, linked_doctype in links:
		value = doc.get(fieldname)
		if not value:
			continue
		if not frappe.get_meta(linked_doctype).has_field("company"):
			continue
		other = frappe.db.get_value(linked_doctype, value, "company")
		if other and other != company:
			label = frappe.get_meta(doc.doctype).get_label(fieldname) or fieldname
			frappe.throw(
				_("{0} {1} belongs to company {2}, but this {3} belongs to {4}. Cross-company links are not allowed.").format(
					_(linked_doctype), frappe.bold(value), frappe.bold(other), _(doc.doctype), frappe.bold(company)
				),
				title=_("Cross-Company Link"),
			)


def registered_doctypes():
	"""Every doctype registered by any module registry."""
	from a3_sola.registry import all_permission_doctypes

	return all_permission_doctypes()
