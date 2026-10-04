# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Portal list of projects - the Solar Installations, one row per job.

A bespoke list rather than the metadata-driven one, because each column tells a story the
job's own fields do not hold on their own: who it is for and where, the connection the
system will sit on, what is being built, what was offered, and how far the job has got. The
status column is the job's latest completed task - its card from the project board - so
the list reads the way the board does.

Every linked record on the page - consumer, lead, address, package, proposal, loan,
quotation, district, DISCOM, section - is resolved in one query per doctype rather than
one per row, so the page costs the same whether it shows five jobs or a hundred.
"""

import frappe
from frappe.utils import cint, flt, fmt_money, format_date

from a3_sola.www.a3solaportal import fill_shell, require_login
from a3_sola.www.a3solaportal.collections import get_collection, initials, record_route
from a3_sola.www.a3solaportal.project_overview import _task

no_cache = 1

SLUG = "projects"
LIMIT = 100

#: What the status card needs, read from the job's task rows.
STAGE_FIELDS = (
	"parent", "idx", "stage_code", "stage_name", "task_doctype", "task_document", "status",
	"planned_start_date", "planned_date", "due_date", "actual_completion_date",
	"is_sla_breached", "skip_reason", "blocked_reason",
)


def _titles(doctype, ids, field):
	"""id -> title for one doctype, in a single query."""
	ids = {i for i in ids if i}
	if not ids:
		return {}
	rows = frappe.get_all(doctype, filters={"name": ("in", list(ids))},
	                      fields=["name", field], limit_page_length=0)
	return {r["name"]: r.get(field) or r["name"] for r in rows}


def _by_name(doctype, ids, fields):
	"""id -> row for one doctype, in a single query, with the caller's permissions."""
	ids = {i for i in ids if i}
	if not ids:
		return {}
	try:
		rows = frappe.get_list(doctype, filters={"name": ("in", list(ids))}, fields=fields, limit_page_length=0)
	except frappe.PermissionError:
		return {}
	return {r["name"]: r for r in rows}


def _latest_per(doctype, key, ids, fields):
	"""key -> the live record that counts for it: a submitted one ahead of a draft, the newest first.

	The same preference `installation_lead` applies when it resolves a lead's records.
	"""
	ids = [i for i in ids if i]
	if not ids:
		return {}
	try:
		rows = frappe.get_list(
			doctype, filters={key: ("in", ids), "docstatus": ("<", 2)},
			fields=list(dict.fromkeys(list(fields) + [key, "docstatus", "creation"])),
			order_by="docstatus desc, creation desc", limit_page_length=0,
		)
	except frappe.PermissionError:
		return {}
	out = {}
	for r in rows:
		out.setdefault(r.get(key), r)
	return out


def _activity(stages):
	"""The task the status column shows: the last completed one, else the first on the plan."""
	if not stages:
		return None
	done = [s for s in stages if s.status == "Completed"]
	return _task(done[-1] if done else stages[0])


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
	or_filters = None
	if q:
		like = f"%{q}%"
		or_filters = [
			["consumer_name", "like", like], ["consumer_number", "like", like],
			["consumer_mobile", "like", like], ["lead_name", "like", like], ["name", "like", like],
		]

	rows = frappe.get_list(
		"Solar Installation",
		fields=[
			"name", "solar_consumer", "consumer_name", "consumer_mobile", "consumer_number", "lead",
			"solar_package", "system_type", "discom", "discom_section", "connection_type",
			"national_portal_application_id", "solar_proposal", "quotation", "is_financed", "status",
		],
		filters={"docstatus": ("<", 2)}, or_filters=or_filters,
		order_by="modified desc", limit_page_length=LIMIT,
	)
	names = [r.name for r in rows]
	consumer_ids = {r.solar_consumer for r in rows if r.solar_consumer}
	lead_ids = {r.lead for r in rows if r.lead}

	# ---- who and where. The job carries the consumer's name and number; the picture, the
	# village and the address are the consumer's own.
	consumers = _by_name("Solar Consumer", consumer_ids, [
		"name", "consumer_photo", "consumer_number", "mobile_no", "village", "local_body_name",
		"installation_address", "discom", "discom_section", "connection_type", "national_portal_consumer_id",
	])
	leads = _by_name("Lead", lead_ids, ["name", "loan_required", "city", "district"])
	addresses = _by_name("Address", {c.get("installation_address") for c in consumers.values()}, ["name", "city", "county"])
	districts = _titles("Indian District", {l.get("district") for l in leads.values()}, "district_name")
	discoms = _titles("DISCOM", {r.discom for r in rows} | {c.get("discom") for c in consumers.values()}, "discom_name")
	sections = _titles("DISCOM Section", {r.discom_section for r in rows} | {c.get("discom_section") for c in consumers.values()}, "section_name")

	# ---- the job's tasks, for the status card
	stages = frappe.get_all(
		"Installation Stage Log",
		filters={"parenttype": "Solar Installation", "parent": ("in", names or [""])},
		fields=list(STAGE_FIELDS), order_by="parent asc, idx asc", limit_page_length=0,
	) if names else []
	stages_of = {}
	for s in stages:
		stages_of.setdefault(s.parent, []).append(s)

	# ---- what is being built
	packages = _titles("Solar Package", {r.solar_package for r in rows}, "package_name")

	# ---- what was offered: the job's proposal, else the consumer's latest, else the lead's
	proposal_fields = ["name", "proposal_date", "recommended_option_cost", "status"]
	proposals = _by_name("Solar Proposal", {r.solar_proposal for r in rows}, proposal_fields)
	unlinked = [r for r in rows if not proposals.get(r.solar_proposal)]
	by_consumer = _latest_per("Solar Proposal", "solar_consumer", [r.solar_consumer for r in unlinked], proposal_fields)
	by_lead = _latest_per("Solar Proposal", "lead", [r.lead for r in unlinked], proposal_fields)

	# ---- the loan, where there is one: the application's status, else the quotation's
	loans = _latest_per("Loan Application", "solar_installation", names, ["name", "status"])
	quotations = _by_name("Quotation", {r.quotation for r in rows}, ["name", "is_financed", "finance_status"])

	for r in rows:
		consumer = consumers.get(r.solar_consumer) or {}
		lead = leads.get(r.lead) or {}
		addr = addresses.get(consumer.get("installation_address")) or {}
		prop = proposals.get(r.solar_proposal) or by_consumer.get(r.solar_consumer) or by_lead.get(r.lead) or {}
		quotation = quotations.get(r.quotation) or {}
		loan = loans.get(r.name) or {}

		# 1 - who it is for
		r["route"] = record_route(SLUG, r.name)
		r["title"] = r.consumer_name or r.name
		r["photo"] = consumer.get("consumer_photo") or ""
		r["initials"] = initials(r["title"])
		r["number"] = r.consumer_number or consumer.get("consumer_number") or ""
		r["mobile"] = r.consumer_mobile or consumer.get("mobile_no") or ""
		r["tel"] = "".join(c for c in r["mobile"] if c.isdigit() or c == "+")
		location = consumer.get("village") or consumer.get("local_body_name") or addr.get("city") or lead.get("city") or ""
		district = districts.get(lead.get("district")) or addr.get("county") or ""
		# "Athani, Ernakulam" - or just the one when the location is the district town.
		r["place"] = ", ".join(dict.fromkeys(p for p in (location, district) if p))

		# 2 - the connection: the job's own, else the consumer's
		r["discom_name"] = discoms.get(r.discom or consumer.get("discom")) or ""
		r["section_name"] = sections.get(r.discom_section or consumer.get("discom_section")) or ""
		r["connection"] = r.connection_type or consumer.get("connection_type") or ""
		r["portal_id"] = r.national_portal_application_id or consumer.get("national_portal_consumer_id") or ""

		# 3 - the system
		r["package_name"] = packages.get(r.solar_package) or ""

		# 4 - the offer
		r["proposal"] = prop.get("name") or ""
		r["proposal_route"] = record_route("proposals", prop["name"]) if prop else ""
		r["proposal_date"] = format_date(prop.get("proposal_date"), "dd MMM yyyy") if prop.get("proposal_date") else ""
		cost = flt(prop.get("recommended_option_cost"))
		r["proposal_cost"] = fmt_money(cost, currency="INR") if cost else ""
		loan_available = (
			cint(r.is_financed) or lead.get("loan_required") == "Yes" or cint(quotation.get("is_financed")) or bool(loan)
		)
		r["loan_status"] = (loan.get("status") or quotation.get("finance_status") or "Not applied") if loan_available else ""

		# 5 - where the job has got to
		r["activity"] = _activity(stages_of.get(r.name))
		r["status_slug"] = (r.status or "").lower().replace(" ", "-")

	context.collection = {**cfg, "slug": SLUG}
	context.rows = rows
	context.total = len(rows)
	context.limit = LIMIT
	context.q = q
	# A list runs the full width of the page.
	context.main_wide = True
	return context
