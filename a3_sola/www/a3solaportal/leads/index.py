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
from a3_sola.api.leads import LEAD_STATUSES, lead_route

no_cache = 1

LIMIT = 100


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

	# The solar columns are custom fields; ask only for the ones this site has installed
	# so the list still renders on a site where the fixtures have not run yet.
	meta = frappe.get_meta("Lead")
	extra = [f for f in ("city", "state", "subsidy_scheme", "approx_capacity_kw") if meta.has_field(f)]

	leads = frappe.get_list(
		"Lead",
		fields=[
			"name", "lead_name", "company_name",
			"email_id", "mobile_no", "status", "creation", "owner",
		] + extra,
		filters=filters,
		or_filters=or_filters,
		order_by="creation desc",
		limit_page_length=LIMIT,
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

	_add_assignment(leads)

	context.leads = leads
	context.total = len(leads)
	context.limit = LIMIT
	context.q = q
	context.status_filter = status
	# Ordered for the dropdown; the set is unordered.
	context.status_options = [
		"Lead", "Open", "Replied", "Opportunity", "Quotation",
		"Lost Quotation", "Interested", "Converted", "Do Not Contact",
	]
	return context


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
