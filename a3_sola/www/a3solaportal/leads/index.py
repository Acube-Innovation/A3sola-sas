# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Portal list of Leads, read from ERPNext.

Login required. The rows come from `frappe.get_list`, which applies the same permission
rules the desk does - a user sees exactly the leads they are allowed to, no more. The
search and status filters are applied server-side so the permission boundary is never
widened by the client.
"""

import frappe

from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import initials
from a3_sola.api.leads import LEAD_STATUSES, lead_route

no_cache = 1

LIMIT = 100
#: The list's tabs, by whose the lead is: the company's own, or a dealer's (Lead's Dealer).
SCOPES = {"ours": {"a3s_dealer": ["is", "not set"]}, "dealers": {"a3s_dealer": ["is", "set"]}}


def _dealer_options():
	"""The dealers with leads the user may see, by name, each with its number of leads."""
	rows = frappe.get_list("Lead", fields=["a3s_dealer", "count(name) as n"], filters={"a3s_dealer": ["is", "set"]},
		group_by="a3s_dealer", limit_page_length=0)
	names = dict(frappe.get_all("User", filters={"name": ["in", [r.a3s_dealer for r in rows]]},
		fields=["name", "full_name"], as_list=True)) if rows else {}
	return sorted(({"value": r.a3s_dealer, "label": names.get(r.a3s_dealer) or r.a3s_dealer, "count": r.n} for r in rows),
		key=lambda d: d["label"].lower())


def _count(filters, or_filters):
	"""How many leads the user may see under these filters."""
	rows = frappe.get_list("Lead", fields=["count(name) as n"], filters=filters, or_filters=or_filters,
		limit_page_length=0)
	return rows[0].n if rows else 0


def get_context(context):
	require_login("/a3solaportal/leads")
	fill_shell(
		context,
		active_route="/a3solaportal/leads",
		page_title="Leads",
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": "Leads"}],
	)

	q = (frappe.form_dict.get("q") or "").strip()
	status = (frappe.form_dict.get("status") or "").strip()
	# Follow Up ticked: the Assignment column shows the outreach stage and next follow-up.
	followup = (frappe.form_dict.get("followup") or "") == "1"

	filters = {}
	if status in LEAD_STATUSES:
		filters["status"] = status

	or_filters = None
	if q:
		# A single term matched across the fields a person would search by. `like` with
		# the term as a parameter - never interpolated - so the search box cannot inject.
		like = f"%{q}%"
		or_filters = [
			["lead_name", "like", like],
			["company_name", "like", like],
			["email_id", "like", like],
			["mobile_no", "like", like],
			["name", "like", like],
		]

	# Whose leads: all, the company's own, or the dealers' - so staff can see and help with a
	# dealer's leads, whose work is the dealer's first. A dealer sees only his own, so no tabs.
	from a3_sola.api.partner_scope import is_partner

	has_dealer = frappe.get_meta("Lead").has_field("a3s_dealer")
	context.show_scope = bool(has_dealer and not is_partner())
	scope = (frappe.form_dict.get("scope") or "").strip()
	scope = scope if context.show_scope and scope in SCOPES else ""
	context.scope = scope
	if context.show_scope:
		context.scope_counts = {key: _count({**filters, **cond}, or_filters) for key, cond in SCOPES.items()}
		context.scope_counts[""] = _count(filters, or_filters)
		filters.update(SCOPES.get(scope, {}))
	# Dealer leads, narrowed to one dealer: those with leads the user may see, by name, with how many.
	context.dealer_options, context.dealer_filter = [], ""
	if scope == "dealers":
		context.dealer_options = _dealer_options()
		dealer = (frappe.form_dict.get("dealer") or "").strip()
		if any(d["value"] == dealer for d in context.dealer_options):
			context.dealer_filter = dealer
			filters["a3s_dealer"] = dealer

	leads = lead_rows(filters, or_filters)

	context.leads = leads
	context.total = len(leads)
	context.limit = LIMIT
	context.q = q
	context.status_filter = status
	context.followup_view = followup
	# Ordered for the dropdown; the set is unordered.
	context.status_options = [
		"Lead", "Open", "Replied", "Opportunity", "Quotation",
		"Lost Quotation", "Interested", "Converted", "Do Not Contact",
	]
	# A list runs the full width of the page.
	context.main_wide = True
	return context


def lead_rows(filters=None, or_filters=None, limit=LIMIT):
	"""Leads as the list shows them, one dict per row: name, place, contact, status, solar
	details, who raised it and who it now sits with. Read with `frappe.get_list`, so the
	caller's own permissions decide which leads come back. The project page shows its lead
	as one of these rows, through the same template the list uses."""
	# The solar columns are custom fields; ask only for the ones this site has installed
	# so the list still renders on a site where the fixtures have not run yet.
	meta = frappe.get_meta("Lead")
	extra = [f for f in ("city", "state", "subsidy_scheme", "approx_capacity_kw", "outreach_stage", "next_followup_date",
		"followup_status", "a3s_dealer") if meta.has_field(f)]

	leads = frappe.get_list(
		"Lead",
		fields=[
			"name", "lead_name", "company_name", "image",
			"email_id", "mobile_no", "status", "creation", "owner",
		] + extra,
		filters=filters,
		or_filters=or_filters,
		order_by="creation desc",
		limit_page_length=limit,
	)
	# Subsidy Scheme is a link to a series-named record; the person wants the scheme's
	# name, not its id, so resolve every scheme on the page in one query.
	scheme_ids = {l.get("subsidy_scheme") for l in leads if l.get("subsidy_scheme")}
	scheme_names = {}
	if scheme_ids:
		scheme_names = dict(
			frappe.get_all("Subsidy Scheme", filters={"name": ["in", list(scheme_ids)]},
			               fields=["name", "scheme_name"], as_list=True)
		)

	for lead in leads:
		lead["display"] = lead.get("lead_name") or lead.get("company_name") or lead["name"]
		lead["initials"] = initials(lead["display"])
		lead["route"] = lead_route(lead["name"])
		# "City, State" under the name; "Scheme, 3 kW" above the status. Either half may
		# be missing, so each line is joined from whatever is present.
		lead["place"] = [p for p in (lead.get("city"), lead.get("state")) if p]
		size = frappe.utils.flt(lead.get("approx_capacity_kw"))
		lead["size_kw"] = "{0:g} kW".format(size) if size else ""
		scheme = lead.get("subsidy_scheme")
		lead["scheme_name"] = scheme_names.get(scheme) or scheme or ""
		lead["solar"] = [p for p in (lead["scheme_name"], lead["size_kw"]) if p]
		lead["created"] = frappe.utils.format_date(lead.get("creation"), "medium")
		# The follow-up view: where the lead is on the cadence, and when it is next followed up.
		lead["next_followup"] = frappe.utils.format_date(lead.get("next_followup_date"), "medium") if lead.get("next_followup_date") else ""
		lead["followup_due"] = lead.get("followup_status") == "FOLLOW UP DUE"

	_add_assignment(leads)
	# A dealer's lead names its dealer, so staff see whose it is first.
	dealers = {l.get("a3s_dealer") for l in leads if l.get("a3s_dealer")}
	dealer_names = dict(frappe.get_all("User", filters={"name": ["in", list(dealers)]}, fields=["name", "full_name"],
		as_list=True)) if dealers else {}
	for lead in leads:
		lead["dealer_name"] = dealer_names.get(lead.get("a3s_dealer")) or lead.get("a3s_dealer") or ""
	return leads


def _add_assignment(leads):
	"""Who raised each lead and who it now sits with.

	Both halves in one column, because the question a person asks of a list is "whose is
	this and how long has it been waiting" - which is two facts, not two columns. The
	names and the assignments are fetched once for the whole page rather than per row.
	"""
	if not leads:
		return

	owners = {l.get("owner") for l in leads if l.get("owner")}
	names = dict(
		frappe.get_all("User", filters={"name": ("in", list(owners))},
		               fields=["name", "full_name"], as_list=True)
	) if owners else {}

	# The newest open assignment per lead, in one query rather than one per row.
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Lead", "reference_name": ("in", [l["name"] for l in leads]),
		         "status": ("!=", "Cancelled")},
		fields=["name", "reference_name", "allocated_to", "description", "creation"],
		order_by="creation asc",
		limit_page_length=0,
		ignore_permissions=True,
	)
	latest = {}
	for row in todos:
		latest[row.reference_name] = row  # ascending, so the last one written wins
	assignee_ids = {r.allocated_to for r in latest.values() if r.allocated_to}
	if assignee_ids:
		names.update(dict(
			frappe.get_all("User", filters={"name": ("in", list(assignee_ids))},
			               fields=["name", "full_name"], as_list=True)
		))

	today = frappe.utils.today()
	for lead in leads:
		lead["created_by"] = names.get(lead.get("owner")) or lead.get("owner") or "—"
		days = frappe.utils.date_diff(today, lead.get("creation"))
		lead["age_days"] = max(frappe.utils.cint(days), 0)
		row = latest.get(lead["name"])
		if row:
			lead["assigned_to"] = names.get(row.allocated_to) or row.allocated_to or ""
			lead["assigned_on"] = frappe.utils.format_date(row.creation, "medium")
			lead["assigned_for"] = frappe.utils.strip_html(row.description or "").strip()
			lead["assigned_todo"] = row.name
		else:
			lead["assigned_to"] = ""
			lead["assigned_todo"] = ""
