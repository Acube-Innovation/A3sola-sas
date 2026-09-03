# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seventeen ways to try to read another tenant's data, and the machinery to run them all.

WHY THIS IS BUILT THE WAY IT IS

*It iterates the registries.* A doctype added in a later phase is attacked automatically. A
hand-written list is correct on the day it is written and stale by the next release, and
the one doctype somebody forgot is exactly the one that leaks.

*It runs as the real user.* `frappe.set_user`, with a restore in `finally`. Asserting on the
permission-query string tests the code that builds the filter; it does not test what the
customer actually experiences, and the difference between those two is where the bugs are.

*A blocked read and a raised error are both passes; a returned row is a failure.* Several
vectors below can fail "safely" in more than one way, and the suite does not care which -
it cares only that no foreign data came back.

*Zero successes is the only acceptable result.* Anything else is a Blocker and fails the
run rather than warning.
"""

import json

import frappe
from frappe.utils import cint

#: Attack outcomes. Only LEAKED is a failure.
BLOCKED = "blocked"      # the attempt raised, or returned nothing - what should happen
LEAKED = "leaked"        # foreign data came back. A Blocker.
SKIPPED = "skipped"      # could not be attempted, with a stated reason


class Attempt:
	"""One attack, its target, and what came back."""

	__slots__ = ("vector", "doctype", "actor", "target", "outcome", "detail", "evidence")

	def __init__(self, vector, doctype, actor, target, outcome, detail="", evidence=None):
		self.vector = vector
		self.doctype = doctype
		self.actor = actor
		self.target = target
		self.outcome = outcome
		self.detail = detail
		self.evidence = evidence

	def as_dict(self):
		return {
			"vector": self.vector, "doctype": self.doctype, "actor": self.actor,
			"target": self.target, "outcome": self.outcome, "detail": self.detail,
			"evidence": self.evidence,
		}

	def __repr__(self):
		return f"<{self.outcome} {self.vector} {self.doctype} as {self.actor}>"


def company_scoped_doctypes():
	"""Every registered doctype that carries a company, from the registries.

	Read from the registry rather than from a list, so a doctype added later is attacked
	without anybody remembering to add it here.
	"""
	from a3_sola import registry

	out = []
	for doctype in sorted(set(registry.all_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle:
			continue
		if not meta.get_field("company"):
			continue
		out.append(doctype)
	return out


def platform_private_doctypes():
	"""Your own business records. A customer must never read any of them."""
	from a3_sola.api.isolation import PLATFORM_PRIVATE_DOCTYPES

	return [d for d in PLATFORM_PRIVATE_DOCTYPES if frappe.db.exists("DocType", d)]


def foreign_records(doctype, company, limit=3):
	"""A few real record names belonging to `company`, read as Administrator."""
	try:
		return frappe.get_all(doctype, filters={"company": company}, pluck="name",
		                      limit=limit, ignore_permissions=True)
	except Exception:
		return []


# ---------------------------------------------------------------- the vectors
def v01_list_view(actor, doctype, foreign_company, foreign_names):
	"""Vector 1 - the ordinary list view. `get_list` applies permissions; `get_all` does
	not, which is why the whole suite uses `get_list`."""
	try:
		rows = frappe.get_list(doctype, filters={"company": foreign_company},
		                       pluck="name", limit_page_length=20)
	except frappe.PermissionError:
		return Attempt("list_view", doctype, frappe.session.user, foreign_company, BLOCKED,
		               "PermissionError")
	if rows:
		return Attempt("list_view", doctype, frappe.session.user, foreign_company, LEAKED,
		               f"{len(rows)} foreign record(s) listed", rows[:5])
	return Attempt("list_view", doctype, frappe.session.user, foreign_company, BLOCKED,
	               "empty result")


def v02_direct_get(actor, doctype, foreign_company, foreign_names):
	"""Vector 2 - straight to a known name, bypassing any list filter."""
	if not foreign_names:
		return Attempt("direct_get", doctype, frappe.session.user, foreign_company, SKIPPED,
		               "no foreign record exists to attempt")
	name = foreign_names[0]
	try:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
	except (frappe.PermissionError, frappe.DoesNotExistError):
		return Attempt("direct_get", doctype, frappe.session.user, name, BLOCKED, "refused")
	except Exception as exception:
		return Attempt("direct_get", doctype, frappe.session.user, name, BLOCKED,
		               type(exception).__name__)
	return Attempt("direct_get", doctype, frappe.session.user, name, LEAKED,
	               "read a foreign document", name)


def v03_client_api(actor, doctype, foreign_company, foreign_names):
	"""Vector 3 - frappe.client.get / get_list / get_value / get_count over the REST layer.

	These are separate code paths from `frappe.get_doc`, and each has its own permission
	handling. A guard on one does not imply a guard on the others.
	"""
	from frappe import client

	if not foreign_names:
		return [Attempt("client_api", doctype, frappe.session.user, foreign_company, SKIPPED,
		                "no foreign record exists to attempt")]
	name = foreign_names[0]
	out = []
	for label, call in (
		("client.get", lambda: client.get(doctype, name)),
		("client.get_value", lambda: client.get_value(doctype, "name", {"name": name})),
		("client.get_list", lambda: client.get_list(
			doctype, filters=json.dumps({"company": foreign_company}), limit_page_length=20)),
		("client.get_count", lambda: client.get_count(
			doctype, filters=json.dumps({"company": foreign_company}))),
	):
		try:
			result = call()
		except Exception as exception:
			out.append(Attempt(label, doctype, frappe.session.user, name, BLOCKED,
			                   type(exception).__name__))
			continue
		leaked = bool(result) and not (
			label == "client.get_count" and not cint(result)
		)
		out.append(Attempt(
			label, doctype, frappe.session.user, name,
			LEAKED if leaked else BLOCKED,
			"returned data" if leaked else "empty",
			str(result)[:160] if leaked else None,
		))
	return out


def v04_reports(actor, report_name, foreign_company, own_company):
	"""Vector 4 - every report, with a foreign company filter AND with none at all.

	The no-filter case matters more. A report that refuses an explicit foreign company but
	returns every company when asked for none is the more common bug and the worse one.
	"""
	from frappe.desk.query_report import run as run_report

	out = []
	for label, filters in (
		("report_foreign_filter", {"company": foreign_company}),
		("report_no_filter", {}),
	):
		try:
			# Through the whitelisted endpoint, not `execute_script_report`. The internal
			# executor skips the role and ref-doctype permission checks, so attacking it
			# proves nothing about what an attacker can actually reach - it only produces
			# false positives for every report correctly restricted to Platform roles.
			result = run_report(report_name, filters=filters, are_default_filters=False)
			rows = (result or {}).get("result") or []
		except frappe.PermissionError:
			out.append(Attempt(label, report_name, frappe.session.user, foreign_company,
			                   BLOCKED, "PermissionError"))
			continue
		except Exception as exception:
			out.append(Attempt(label, report_name, frappe.session.user, foreign_company,
			                   BLOCKED, type(exception).__name__))
			continue
		foreign_rows = [r for r in (rows or []) if _row_company(r) == foreign_company]
		out.append(Attempt(
			label, report_name, frappe.session.user, foreign_company,
			LEAKED if foreign_rows else BLOCKED,
			f"{len(foreign_rows)} foreign row(s)" if foreign_rows else "no foreign rows",
			foreign_rows[:2] if foreign_rows else None,
		))
	return out


def _row_company(row):
	if isinstance(row, dict):
		return row.get("company")
	return getattr(row, "company", None)


def v05_link_search(actor, doctype, foreign_company, foreign_names):
	"""Vector 5 - the link field dropdown and the awesome bar.

	Tested separately because it leaks NAMES even when reads are blocked, and a consumer
	number or an organisation name is itself commercially sensitive.
	"""
	from frappe.desk.search import search_link, search_widget

	if not foreign_names:
		return [Attempt("link_search", doctype, frappe.session.user, foreign_company,
		                SKIPPED, "no foreign record exists to attempt")]
	needle = foreign_names[0]
	out = []
	for label, call in (
		("link_search", lambda: search_link(doctype, needle)),
		("search_widget", lambda: search_widget(doctype, needle)),
	):
		try:
			call()
			results = frappe.response.get("results") or frappe.response.get("values") or []
		except Exception as exception:
			out.append(Attempt(label, doctype, frappe.session.user, needle, BLOCKED,
			                   type(exception).__name__))
			continue
		finally:
			frappe.response.pop("results", None)
			frappe.response.pop("values", None)
		hits = [r for r in results if needle in str(r)]
		out.append(Attempt(label, doctype, frappe.session.user, needle,
		                   LEAKED if hits else BLOCKED,
		                   "suggested a foreign record" if hits else "no suggestions",
		                   hits[:3] if hits else None))
	return out


def v06_print_and_pdf(actor, doctype, foreign_company, foreign_names):
	"""Vector 6 - print view and PDF for a foreign document name."""
	from frappe.www.printview import get_html_and_style

	if not foreign_names:
		return Attempt("print_view", doctype, frappe.session.user, foreign_company, SKIPPED,
		               "no foreign record exists to attempt")
	name = foreign_names[0]
	try:
		html = get_html_and_style(doc=frappe.as_json({"doctype": doctype, "name": name}),
		                          name=name, doctype=doctype)
	except Exception as exception:
		return Attempt("print_view", doctype, frappe.session.user, name, BLOCKED,
		               type(exception).__name__)
	body = (html or {}).get("html") or ""
	if name in body:
		return Attempt("print_view", doctype, frappe.session.user, name, LEAKED,
		               "rendered a foreign document", name)
	return Attempt("print_view", doctype, frappe.session.user, name, BLOCKED,
	               "nothing rendered")


def v07_private_files(actor, foreign_company, foreign_names_by_doctype):
	"""Vector 7 - a private file attached to a foreign document, fetched by its URL.

	A common isolation gap: the document is protected and the attachment is not.
	"""
	out = []
	files = frappe.get_all(
		"File",
		filters={"is_private": 1, "attached_to_doctype": ["in", list(foreign_names_by_doctype)]},
		fields=["name", "file_url", "attached_to_doctype", "attached_to_name"],
		limit=10, ignore_permissions=True,
	)
	targeted = [
		f for f in files
		if f.attached_to_name in (foreign_names_by_doctype.get(f.attached_to_doctype) or [])
	]
	if not targeted:
		return [Attempt("private_file", "File", frappe.session.user, foreign_company, SKIPPED,
		                "no private file is attached to a foreign document")]
	for row in targeted[:5]:
		try:
			doc = frappe.get_doc("File", row.name)
			doc.check_permission("read")
			readable = True
		except Exception:
			readable = False
		out.append(Attempt("private_file", "File", frappe.session.user, row.file_url,
		                   LEAKED if readable else BLOCKED,
		                   "read a foreign private file" if readable else "refused"))
	return out


def v08_export(actor, doctype, foreign_company, foreign_names):
	"""Vector 8 - export. `frappe.desk.query_report` and the list-view export both build
	their own queries, so a guard on the list view does not cover them."""
	try:
		from frappe.desk.reportview import export_query

		frappe.form_dict.update({
			"doctype": doctype, "file_format_type": "CSV",
			"filters": json.dumps({"company": foreign_company}),
			"fields": json.dumps([f"`tab{doctype}`.`name`"]),
			"visible_idx": json.dumps([0]),
		})
		export_query()
		body = frappe.response.get("result") or frappe.response.get("filecontent") or ""
	except Exception as exception:
		return Attempt("export", doctype, frappe.session.user, foreign_company, BLOCKED,
		               type(exception).__name__)
	finally:
		for key in ("result", "filecontent", "filename", "type"):
			frappe.response.pop(key, None)
		frappe.form_dict.clear()
	hits = [n for n in foreign_names if n and n in str(body)]
	return Attempt("export", doctype, frappe.session.user, foreign_company,
	               LEAKED if hits else BLOCKED,
	               "exported foreign rows" if hits else "no foreign rows",
	               hits[:3] if hits else None)


def v09_bulk_endpoints(actor, doctype, foreign_company, foreign_names):
	"""Vector 9 - Frappe's standard bulk endpoints against a foreign name.

	Writing to a foreign record is worse than reading one, so these are attempted even
	though a read block usually implies a write block.
	"""
	if not foreign_names:
		return [Attempt("bulk_write", doctype, frappe.session.user, foreign_company, SKIPPED,
		                "no foreign record exists to attempt")]
	name = foreign_names[0]
	out = []
	for label, call in (
		("bulk_set_value", lambda: frappe.client.set_value(doctype, name, "modified_by",
		                                                   frappe.session.user)),
		("bulk_delete", lambda: frappe.client.delete(doctype, name)),
	):
		try:
			call()
		except Exception as exception:
			out.append(Attempt(label, doctype, frappe.session.user, name, BLOCKED,
			                   type(exception).__name__))
			continue
		out.append(Attempt(label, doctype, frappe.session.user, name, LEAKED,
		                   "WROTE TO a foreign document", name))
	return out


def v10_dashboard_aggregates(actor, foreign_company, own_company):
	"""Vector 10 - number cards and charts.

	An aggregate that includes foreign rows leaks information without exposing a single
	record: a competitor's pipeline value is a number worth having.
	"""
	out = []
	for card in frappe.get_all("Number Card", filters={"module": ["like", "Solar%"]},
	                           fields=["name", "document_type", "filters_json"], limit=25):
		if not card.document_type or not frappe.db.exists("DocType", card.document_type):
			continue
		meta = frappe.get_meta(card.document_type)
		if meta.istable or not meta.get_field("company"):
			continue
		try:
			total = len(frappe.get_list(card.document_type, pluck="name",
			                            limit_page_length=0))
			foreign = len(frappe.get_all(card.document_type,
			                             filters={"company": foreign_company},
			                             pluck="name", ignore_permissions=True))
			mine = len(frappe.get_all(card.document_type,
			                          filters={"company": own_company},
			                          pluck="name", ignore_permissions=True))
		except Exception as exception:
			out.append(Attempt("dashboard_aggregate", card.document_type,
			                   frappe.session.user, card.name, BLOCKED,
			                   type(exception).__name__))
			continue
		# The visible count must not exceed what this tenant owns.
		leaked = total > mine and foreign > 0
		out.append(Attempt("dashboard_aggregate", card.document_type, frappe.session.user,
		                   card.name, LEAKED if leaked else BLOCKED,
		                   f"visible {total}, own {mine}, foreign {foreign}"))
	return out


def v11_global_search(actor, needle, foreign_company):
	"""Vector 11 - global search for a string that exists only in foreign data."""
	from frappe.utils.global_search import search

	try:
		results = search(needle, limit=20)
	except Exception as exception:
		return Attempt("global_search", "__Global Search", frappe.session.user, needle,
		               BLOCKED, type(exception).__name__)
	hits = [r for r in (results or []) if needle.lower() in str(r).lower()]
	return Attempt("global_search", "__Global Search", frappe.session.user, needle,
	               LEAKED if hits else BLOCKED,
	               "found foreign content" if hits else "no results",
	               str(hits[:2]) if hits else None)


def v12_timeline(actor, doctype, foreign_company, foreign_names):
	"""Vector 12 - comments, versions and activity on a foreign document.

	The timeline is a separate read path and has historically been a way to read field
	values out of a document you cannot open.
	"""
	if not foreign_names:
		return [Attempt("timeline", doctype, frappe.session.user, foreign_company, SKIPPED,
		                "no foreign record exists to attempt")]
	name = foreign_names[0]
	out = []
	for label, dt, filters in (
		("comments", "Comment", {"reference_doctype": doctype, "reference_name": name}),
		("versions", "Version", {"ref_doctype": doctype, "docname": name}),
		("activity", "Activity Log", {"reference_doctype": doctype, "reference_name": name}),
	):
		try:
			rows = frappe.get_list(dt, filters=filters, pluck="name", limit_page_length=10)
		except Exception as exception:
			out.append(Attempt(label, doctype, frappe.session.user, name, BLOCKED,
			                   type(exception).__name__))
			continue
		out.append(Attempt(label, doctype, frappe.session.user, name,
		                   LEAKED if rows else BLOCKED,
		                   f"{len(rows)} row(s)" if rows else "empty"))
	return out


def v16_privilege_escalation(actor, own_tenant, foreign_tenant):
	"""Vector 16 - a tenant admin trying to become something they are not.

	EVERY CHECK HERE ASSERTS ON THE OUTCOME, NOT ON THE ABSENCE OF AN EXCEPTION.

	That distinction is the whole value of this vector. Frappe accepts a save in which a
	user appends a role they may not grant, and then silently discards the row - so a
	suite that treats "the call did not raise" as escalation reports a Blocker that is not
	one, and a suite that treats it as a pass would miss a real one if the strip ever
	stopped happening. Both are useless. What is checked is whether the privilege was
	actually gained and whether foreign data actually became readable.
	"""
	out = []
	me = frappe.session.user

	def attempt(label, call, verify, target):
		"""`call` tries the escalation; `verify` returns True if it actually worked."""
		raised = None
		try:
			call()
		except Exception as exception:
			raised = type(exception).__name__
		try:
			gained = bool(verify())
		except Exception:
			gained = False
		if gained:
			return out.append(Attempt(label, "User", me, target, LEAKED,
			                          "the privilege was actually gained", target))
		out.append(Attempt(label, "User", me, target, BLOCKED,
		                   f"refused ({raised})" if raised
		                   else "accepted the write but the privilege was not gained"))

	def grant_platform_role():
		doc = frappe.get_doc("User", me)
		doc.append("roles", {"role": "Platform Admin"})
		doc.save()

	def holds_platform_role():
		frappe.clear_cache(user=me)
		return "Platform Admin" in frappe.get_roles(me)

	def widen_own_permission():
		rows = frappe.get_all("User Permission",
		                      filters={"user": me, "allow": "Company"}, pluck="name")
		if not rows:
			raise frappe.DoesNotExistError("no user permission to remove")
		for name in rows:
			frappe.delete_doc("User Permission", name)

	def can_now_read_foreign():
		"""The only thing that matters: did removing it actually open anything up?"""
		frappe.clear_cache(user=me)
		company = frappe.db.get_value("Tenant", foreign_tenant, "company")
		if not company:
			return False
		return bool(frappe.get_list("Solar Consumer", filters={"company": company},
		                            pluck="name", limit_page_length=5))

	def raise_own_quota():
		doc = frappe.get_doc("Tenant", own_tenant)
		doc.user_quota = cint(doc.user_quota) + 50
		doc.save()

	def quota_actually_rose(before):
		return cint(frappe.db.get_value("Tenant", own_tenant, "user_quota")) > before

	def read_settings():
		frappe.get_doc("A3 Sola Settings").check_permission("read")

	def settings_readable():
		try:
			frappe.get_doc("A3 Sola Settings").check_permission("read")
			return True
		except Exception:
			return False

	def read_foreign_tenant():
		frappe.get_doc("Tenant", foreign_tenant).check_permission("read")

	def foreign_tenant_readable():
		try:
			frappe.get_doc("Tenant", foreign_tenant).check_permission("read")
			return True
		except Exception:
			return False

	def read_gateway_credentials():
		frappe.get_doc("A3 Sola Settings").check_permission("read")

	def credentials_readable():
		"""A secret is leaked only if the VALUE comes back, not merely the fieldname."""
		if not settings_readable():
			return False
		return bool(frappe.db.get_single_value("A3 Sola Settings", "razorpay_key_secret"))

	quota_before = cint(frappe.db.get_value("Tenant", own_tenant, "user_quota"))

	attempt("escalate_platform_role", grant_platform_role, holds_platform_role,
	        "Platform Admin")
	attempt("remove_own_user_permission", widen_own_permission, can_now_read_foreign, me)
	attempt("raise_own_quota", raise_own_quota,
	        lambda: quota_actually_rose(quota_before), own_tenant)
	attempt("read_settings_singleton", read_settings, settings_readable,
	        "A3 Sola Settings")
	attempt("read_foreign_tenant", read_foreign_tenant, foreign_tenant_readable,
	        foreign_tenant)
	attempt("read_gateway_credentials", read_gateway_credentials, credentials_readable,
	        "razorpay_key_secret")
	return out


def v17_grouped_aggregate(actor, foreign_company, own_company):
	"""Vector 17 - group a report by company and see whose names come back."""
	out = []
	for doctype in company_scoped_doctypes()[:20]:
		try:
			rows = frappe.get_list(doctype, fields=["company", "count(name) as n"],
			                       group_by="company", limit_page_length=0)
		except Exception as exception:
			out.append(Attempt("group_by_company", doctype, frappe.session.user,
			                   foreign_company, BLOCKED, type(exception).__name__))
			continue
		companies = {r.get("company") for r in (rows or []) if r.get("company")}
		foreign = companies - {own_company, None}
		out.append(Attempt("group_by_company", doctype, frappe.session.user, foreign_company,
		                   LEAKED if foreign else BLOCKED,
		                   f"companies visible: {sorted(companies)}" if foreign
		                   else "own company only",
		                   sorted(foreign) if foreign else None))
	return out


def v13_portals(actor, foreign_subscription, foreign_project):
	"""Vector 13 - the customer portal and the billing portal with manipulated parameters.

	These take a document name straight from the request. Passing somebody else's is the
	first thing anybody tries.
	"""
	out = []
	from a3_sola.api import billing_portal

	def attempt(label, call, target):
		try:
			result = call()
		except Exception as exception:
			return out.append(Attempt(label, "portal", frappe.session.user, target, BLOCKED,
			                          type(exception).__name__))
		out.append(Attempt(label, "portal", frappe.session.user, target,
		                   LEAKED if result else BLOCKED,
		                   "returned foreign data" if result else "empty",
		                   str(result)[:160] if result else None))

	if foreign_subscription:
		attempt("billing_portal.my_invoices",
		        lambda: billing_portal.my_invoices(foreign_subscription), foreign_subscription)
		attempt("billing_portal.my_plan",
		        lambda: billing_portal.my_plan(foreign_subscription), foreign_subscription)
		attempt("billing_portal.my_team",
		        lambda: billing_portal.my_team(foreign_subscription), foreign_subscription)
		attempt("billing_portal.my_history",
		        lambda: billing_portal.my_history(foreign_subscription), foreign_subscription)
		attempt("billing_portal.pay_outstanding",
		        lambda: billing_portal.pay_outstanding(foreign_subscription),
		        foreign_subscription)

	try:
		from a3_sola.api import portal

		if foreign_project:
			attempt("customer_portal.project",
			        lambda: portal.my_system(foreign_project), foreign_project)
	except (ImportError, AttributeError):
		out.append(Attempt("customer_portal.project", "portal", frappe.session.user,
		                   foreign_project, SKIPPED, "no matching portal entry point"))
	return out


def v14_public_endpoints(foreign_signup, foreign_token):
	"""Vector 14 - the public funnel with a foreign reference and a guessed token.

	Run as Guest. These are the only endpoints an unauthenticated attacker can reach at
	all, so a weakness here needs no account to exploit.
	"""
	out = []
	candidates = []
	for module_path in ("a3_sola.api.signup", "a3_sola.api.payments",
	                    "a3_sola.api.invitations"):
		try:
			module = frappe.get_module(module_path)
		except Exception:
			continue
		for name in dir(module):
			fn = getattr(module, name)
			if callable(fn) and is_whitelisted(fn) and is_guest_method(fn):
				candidates.append((f"{module_path}.{name}", fn))

	for path, fn in candidates:
		for label, argument in (("foreign_reference", foreign_signup),
		                        ("guessed_token", foreign_token)):
			if not argument:
				continue
			try:
				result = _call_with_one_reference(fn, argument)
			except Exception as exception:
				out.append(Attempt(f"public::{label}", path, "Guest", argument, BLOCKED,
				                   type(exception).__name__))
				continue
			if result is SKIPPED:
				out.append(Attempt(f"public::{label}", path, "Guest", argument, SKIPPED,
				                   "takes no document reference"))
				continue
			leaked = _looks_like_a_leak(result, argument)
			out.append(Attempt(f"public::{label}", path, "Guest", argument,
			                   LEAKED if leaked else BLOCKED,
			                   "returned data for a foreign reference" if leaked else "refused",
			                   str(result)[:160] if leaked else None))
	return out


def v15_every_whitelisted_method(foreign_name, foreign_company):
	"""Vector 15 - EVERY whitelisted method in the app, called with a foreign reference.

	Enumerated from the modules rather than listed, which is the point: a method added in
	a later phase cannot escape this suite by nobody remembering it. Methods that plainly
	take no document reference are skipped and counted as skipped, not as passes.
	"""
	out = []
	for path, fn in whitelisted_methods():
		try:
			result = _call_with_one_reference(fn, foreign_name)
		except Exception as exception:
			out.append(Attempt("whitelisted_method", path, frappe.session.user, foreign_name,
			                   BLOCKED, type(exception).__name__))
			continue
		if result is SKIPPED:
			out.append(Attempt("whitelisted_method", path, frappe.session.user, foreign_name,
			                   SKIPPED, "takes no document reference"))
			continue
		leaked = _looks_like_a_leak(result, foreign_name)
		out.append(Attempt("whitelisted_method", path, frappe.session.user, foreign_name,
		                   LEAKED if leaked else BLOCKED,
		                   "returned data for a foreign reference" if leaked else "refused",
		                   str(result)[:160] if leaked else None))
	return out


#: Parameter names that mean "the document this acts on".
REFERENCE_ARGUMENTS = (
	"name", "docname", "doc", "document", "tenant", "subscription",
	"platform_subscription", "installation", "solar_installation", "project",
	"consumer", "solar_consumer", "signup", "invitation", "order", "payment_order",
	"invoice", "reference_name", "suspension", "request", "contract", "om_contract",
	"ticket", "service_ticket", "estimate", "proposal", "quotation", "billing_plan",
	"claim", "job", "commissioning_report", "token",
)


def whitelisted_methods(include_guest=True):
	"""Every @frappe.whitelist() method in the app, found by walking the package.

	Walked rather than listed. The whole value of this vector is that it cannot be
	out of date.
	"""
	import importlib
	import pkgutil

	import a3_sola

	found = {}
	for info in pkgutil.walk_packages(a3_sola.__path__, prefix="a3_sola."):
		if ".tests" in info.name or "__pycache__" in info.name:
			continue
		try:
			module = importlib.import_module(info.name)
		except Exception:
			continue
		for attribute in dir(module):
			fn = getattr(module, attribute, None)
			if not callable(fn) or not is_whitelisted(fn):
				continue
			if getattr(fn, "__module__", "") != info.name:
				continue  # imported into this module, owned by another
			if not include_guest and is_guest_method(fn):
				continue
			found[f"{info.name}.{attribute}"] = fn
	return sorted(found.items())


def is_whitelisted(fn):
	"""Membership in `frappe.whitelisted`, not an attribute on the function.

	`frappe.whitelist()` appends to a module-level list and sets nothing on the function
	itself, so `getattr(fn, "whitelisted", False)` is always False - which silently made
	the whole endpoint sweep attempt nothing at all. A security suite that quietly tests
	zero endpoints is worse than not having one.
	"""
	target = getattr(fn, "__func__", fn)
	return fn in frappe.whitelisted or target in frappe.whitelisted


def is_guest_method(fn):
	target = getattr(fn, "__func__", fn)
	return fn in frappe.guest_methods or target in frappe.guest_methods


def _call_with_one_reference(fn, value):
	"""Call `fn` passing `value` as whatever its document-reference argument is called."""
	import inspect

	try:
		signature = inspect.signature(fn)
	except (TypeError, ValueError):
		return SKIPPED
	parameters = list(signature.parameters.values())
	target = None
	for parameter in parameters:
		if parameter.name in REFERENCE_ARGUMENTS:
			target = parameter.name
			break
	if not target:
		return SKIPPED
	# Everything else must have a default, or the call would fail for the wrong reason.
	required = [
		p for p in parameters
		if p.name != target and p.default is inspect.Parameter.empty
		and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
	]
	if required:
		return SKIPPED
	return fn(**{target: value})


def _looks_like_a_leak(result, needle):
	"""Did the call return anything that names the foreign record?"""
	if result in (None, "", [], {}, False):
		return False
	return str(needle) in str(result)
