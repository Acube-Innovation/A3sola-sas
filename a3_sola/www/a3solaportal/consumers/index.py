# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Portal list of Solar Consumers.

A bespoke list rather than the metadata-driven one, because the columns are not one field
each: the customer column carries three ways to reach a person, and the category column
carries what the lead said alongside what the consumer says. The generic list renders a
field per cell, which is right for most collections and wrong for this one.

Every linked record on the page - customer, lead, scheme, roof type, DISCOM, section - is
resolved in one query per doctype rather than one per row, so the page costs the same
whether it shows five consumers or a hundred.
"""

import frappe

from a3_sola.api import assignments
from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import get_collection, initials, record_route

no_cache = 1

SLUG = "consumers"
LIMIT = 100

STATUSES = ("New", "Surveyed", "Designed", "Proposed", "Quoted", "Converted", "Dropped")


def _titles(doctype, ids, field):
	"""id -> title for one doctype, in a single query."""
	ids = {i for i in ids if i}
	if not ids:
		return {}
	rows = frappe.get_all(doctype, filters={"name": ("in", list(ids))},
	                      fields=["name", field], limit_page_length=0)
	return {r["name"]: r.get(field) or r["name"] for r in rows}


def get_context(context):
	require_login("/a3solaportal/" + SLUG)
	cfg = get_collection(SLUG)
	fill_shell(
		context,
		active_route="/a3solaportal/" + SLUG,
		page_title=cfg["title"],
		crumbs=[{"label": "Home", "href": "/a3solaportal/dashboard"}, {"label": cfg["title"]}],
	)

	q = (frappe.form_dict.get("q") or "").strip()
	status = (frappe.form_dict.get("status") or "").strip()

	filters = {}
	if status in STATUSES:
		filters["status"] = status

	or_filters = None
	if q:
		like = f"%{q}%"
		or_filters = [
			["consumer_name", "like", like], ["consumer_number", "like", like],
			["mobile_no", "like", like], ["email_id", "like", like], ["name", "like", like],
		]

	rows = frappe.get_list(
		"Solar Consumer",
		fields=[
			"name", "consumer_name", "consumer_photo", "consumer_number",
			"customer", "email_id", "mobile_no",
			"lead", "consumer_category", "roof_type",
			"discom", "discom_section", "status",
		],
		filters=filters, or_filters=or_filters,
		order_by="modified desc", limit_page_length=LIMIT,
	)

	# The scheme is the lead's, so the leads on this page are read once and their schemes
	# resolved from that - two queries, not two per row.
	lead_ids = {r.lead for r in rows if r.lead}
	leads = {}
	if lead_ids:
		leads = {
			l["name"]: l for l in frappe.get_all(
				"Lead", filters={"name": ("in", list(lead_ids))},
				fields=["name", "subsidy_scheme"], limit_page_length=0,
			)
		}
	schemes = _titles("Subsidy Scheme", {l.get("subsidy_scheme") for l in leads.values()}, "scheme_name")
	customers = _titles("Customer", {r.customer for r in rows}, "customer_name")
	roofs = _titles("Roof Type", {r.roof_type for r in rows}, "roof_type")
	discoms = _titles("DISCOM", {r.discom for r in rows}, "discom_name")
	sections = _titles("DISCOM Section", {r.discom_section for r in rows}, "section_name")

	# Who each consumer sits with, for the status column. One query for the page.
	todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Solar Consumer",
		         "reference_name": ("in", [r.name for r in rows] or [""]),
		         "status": ("!=", "Cancelled")},
		fields=["name", "reference_name", "allocated_to", "creation"],
		order_by="creation asc", limit_page_length=0, ignore_permissions=True,
	)
	latest = {t.reference_name: t for t in todos}
	people = _titles("User", {t.allocated_to for t in latest.values()}, "full_name")

	for r in rows:
		r["route"] = record_route(SLUG, r.name)
		r["initials"] = initials(r.consumer_name or r.name)
		r["customer_name"] = customers.get(r.customer) or ""
		r["customer_route"] = "/app/customer/{0}".format(frappe.utils.quote(r.customer)) if r.customer else ""
		r["lead_route"] = "/a3solaportal/leads/{0}".format(frappe.utils.quote(r.lead)) if r.lead else ""
		lead = leads.get(r.lead) or {}
		r["scheme_name"] = schemes.get(lead.get("subsidy_scheme")) or ""
		r["roof_name"] = roofs.get(r.roof_type) or ""
		r["discom_name"] = discoms.get(r.discom) or ""
		r["section_name"] = sections.get(r.discom_section) or ""
		r["status_slug"] = (r.status or "").lower().replace(" ", "-")
		todo = latest.get(r.name)
		r["assigned_to"] = (people.get(todo.allocated_to) or todo.allocated_to) if todo else ""
		r["assigned_todo"] = todo.name if todo else ""
		# A number is dialled, not read, so it is offered as a call.
		r["tel"] = "".join(c for c in (r.mobile_no or "") if c.isdigit() or c == "+")

	context.collection = {**cfg, "slug": SLUG}
	context.rows = rows
	context.total = len(rows)
	context.limit = LIMIT
	context.q = q
	context.status = status
	context.statuses = STATUSES
	context.csrf_token = frappe.sessions.get_csrf_token()
	return context
