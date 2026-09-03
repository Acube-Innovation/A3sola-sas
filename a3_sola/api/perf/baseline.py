# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The baseline: what everything costs today, measured rather than judged."""

import frappe
from frappe.utils import today

from a3_sola.api.perf.bench import measure, render_console, render_table

MODULES = ("Solar CRM", "Solar Operations", "Solar Projects", "Platform")


def heaviest_doctypes(limit=10):
	"""The ten doctypes with the most rows - where a slow list view actually hurts."""
	from a3_sola import registry

	counts = []
	for doctype in sorted(set(registry.all_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle:
			continue
		try:
			counts.append((frappe.db.count(doctype), doctype))
		except Exception:
			continue
	counts.sort(reverse=True)
	return [doctype for _count, doctype in counts[:limit]]


def list_views(runs=7):
	"""What the desk does when somebody opens a list: 20 rows, newest first."""
	out = []
	for doctype in heaviest_doctypes():
		out.append(measure(
			f"list: {doctype}",
			lambda d=doctype: frappe.get_list(
				d, fields=["name", "modified"], limit_page_length=20,
				order_by="modified desc"),
			runs=runs,
		))
	return out


def reports(runs=3):
	"""Every report in the app, with no filters - the worst case a user can produce."""
	from frappe.desk.query_report import run as run_report

	out = []
	for name in frappe.get_all("Report", filters={"module": ["in", MODULES], "disabled": 0},
	                           pluck="name"):
		out.append(measure(
			f"report: {name}",
			lambda n=name: run_report(n, filters={}, are_default_filters=False),
			runs=runs,
		))
	return out


def permission_overhead(runs=15):
	"""The single highest-leverage measurement in the app.

	`permission_query_conditions` runs on EVERY query for a registered doctype. A
	millisecond here is a millisecond on every list, report and link lookup in the
	product, so it is measured on its own rather than inferred from the list timings.
	"""
	from a3_sola.api import permissions

	company_doctype = "Solar Consumer"
	user = frappe.session.user
	out = [
		measure("permission_query_conditions (one call)",
		        lambda: permissions.build_query_conditions(user, company_doctype),
		        runs=runs),
		measure("get_list WITH permission hook",
		        lambda: frappe.get_list(company_doctype, limit_page_length=20), runs=runs),
		measure("get_all WITHOUT permission hook (control)",
		        lambda: frappe.get_all(company_doctype, limit_page_length=20), runs=runs),
	]
	return out


def access_gate(runs=25):
	"""Phase 7's per-request gate. It runs on every authenticated request, so its cost is
	added to everything."""
	from a3_sola.api.lifecycle import gate
	from a3_sola.api.entitlements import TENANT_FIELD

	user = frappe.db.get_value("User", {TENANT_FIELD: ["is", "set"], "enabled": 1}, "name")
	if not user:
		return [measure("access gate: no tenant user on this site", lambda: None, runs=1)]
	gate.invalidate(user=user)
	return [
		measure("access gate: cold (cache miss)",
		        lambda: (gate.invalidate(user=user), gate.gate_for(user)), runs=runs),
		measure("access gate: warm (cached)", lambda: gate.gate_for(user), runs=runs),
	]


def public_pages(runs=5):
	"""The marketing site as a guest, and the two logged-in portals."""
	from a3_sola.api import platform

	out = [
		measure("public: published plans", lambda: platform.get_published_plans(), runs=runs),
		measure("public: plan total",
		        lambda: platform.calculate_plan_total("starter", "monthly", 0), runs=runs),
	]
	subscription = frappe.db.get_value("Platform Subscription", {"docstatus": 1}, "name")
	if subscription:
		from a3_sola.api import billing_portal

		out.append(measure("portal: my_subscriptions",
		                   lambda: billing_portal.my_subscriptions(), runs=runs))
		out.append(measure("portal: my_invoices",
		                   lambda: billing_portal.my_invoices(subscription), runs=runs))
	return out


def schedulers(runs=1):
	"""Each nightly job, end to end. These have a window; the others have a user waiting."""
	jobs = []

	def add(label, path):
		try:
			fn = frappe.get_attr(path)
		except Exception:
			return
		jobs.append(measure(f"scheduler: {label}", fn, runs=runs, warmup=0))

	add("lifecycle engine (Phase 7)", "a3_sola.api.lifecycle.engine.run_lifecycle")
	add("daily billing (Phase 5)", "a3_sola.api.billing_engine.run_daily_billing")
	add("dunning (Phase 5)", "a3_sola.api.dunning.run_dunning")
	add("stage escalation (Phase 2)", "a3_sola.api.escalation.daily_escalation")
	add("SLA scan (Phase 3)", "a3_sola.api.sla.hourly_sla_scan")
	add("O&M visits due (Phase 3)", "a3_sola.api.om.mark_due_and_missed_visits")
	add("renewal detection (Phase 3)", "a3_sola.api.om.detect_renewals")
	add("usage drift (Phase 6)", "a3_sola.api.entitlements.recalculate_all_usage")
	add("follow-up scan (Phase 1)", "a3_sola.api.outreach.daily_followup_scan")
	return jobs


def run_all():
	"""Everything, as one report."""
	sections = [
		("List views on the ten heaviest doctypes", list_views()),
		("Permission layer", permission_overhead()),
		("Access gate (Phase 7)", access_gate()),
		("Public and portal", public_pages()),
		("Reports", reports()),
		("Schedulers", schedulers()),
	]
	return sections


def render(sections):
	return "\n\n".join(render_table(rows, title) for title, rows in sections)


def console(sections):
	return "\n\n".join(render_console(rows, title) for title, rows in sections)
