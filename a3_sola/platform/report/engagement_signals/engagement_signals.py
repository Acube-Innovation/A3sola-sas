# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Engagement Signals.

The leading indicator of churn, and a far better one than payment status. A tenant who has
paid every invoice and whose team has not opened the app in six weeks is going to cancel;
you just have not been told yet. The "never used" column is where the conversation starts.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today

from a3_sola.api.entitlements import TENANT_FIELD

MODULES = ("Solar CRM", "Solar Operations", "Solar Projects")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 145},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 195},
		{"label": _("State"), "fieldname": "status", "fieldtype": "Data", "width": 95},
		{"label": _("Last Login"), "fieldname": "last_login", "fieldtype": "Datetime", "width": 155},
		{"label": _("Days Quiet"), "fieldname": "days_quiet", "fieldtype": "Int", "width": 95},
		{"label": _("Users Active (30d)"), "fieldname": "active_30", "fieldtype": "Int", "width": 140},
		{"label": _("Seats"), "fieldname": "seats", "fieldtype": "Data", "width": 80},
		{"label": _("Documents (30d)"), "fieldname": "documents_30", "fieldtype": "Int", "width": 135},
		{"label": _("Modules Never Used"), "fieldname": "unused_modules", "fieldtype": "Data", "width": 260},
		{"label": _("Read This As"), "fieldname": "verdict", "fieldtype": "Data", "width": 300},
	]


def get_data(filters):
	"""One pass, batched.

	This read fourteen queries per tenant - a user query, a name lookup, six document
	counts and six module probes - which is 229 queries to produce eleven rows. Every one
	of those is the same question asked once per tenant, so each is now asked once for all
	of them and answered from a dict.
	"""
	cutoff = add_days(today(), -30)
	tenants = frappe.get_all(
		"Tenant", filters={"status": ["in", ["Active", "Suspended"]]},
		fields=["name", "tenant_name", "company", "platform_subscription", "user_quota",
		        "active_users", "status"],
	)
	if not tenants:
		return []

	companies = [t.company for t in tenants if t.company] or [""]
	subscriptions = [t.platform_subscription for t in tenants if t.platform_subscription] or [""]

	# 1. Organisation names - one query, not one per tenant.
	names = {
		r.name: r.organisation_name
		for r in frappe.get_all("Platform Subscription",
		                        filters={"name": ["in", subscriptions]},
		                        fields=["name", "organisation_name"])
	}

	# 2. Users and their last login - one query for every tenant at once.
	users_by_tenant = {}
	for row in frappe.get_all("User", filters={TENANT_FIELD: ["in", [t.name for t in tenants]]},
	                          fields=["name", "last_login", "enabled", TENANT_FIELD]):
		users_by_tenant.setdefault(row.get(TENANT_FIELD), []).append(row)

	# 3. Document counts, grouped by company - one query per doctype rather than per
	#    doctype per tenant.
	recent, ever = _counts_by_company(companies, cutoff)

	rows = []
	for tenant in tenants:
		users = users_by_tenant.get(tenant.name, [])
		logins = [u.last_login for u in users if u.last_login]
		last_login = max(logins) if logins else None
		active_30 = len([d for d in logins if getdate(d) >= getdate(cutoff)])
		documents = sum(recent.get(tenant.company, {}).values())
		unused = _unused_from(ever.get(tenant.company, {}))
		quiet = date_diff(today(), getdate(last_login)) if last_login else None

		rows.append({
			"tenant": tenant.name,
			"organisation_name": names.get(tenant.platform_subscription) or tenant.tenant_name,
			"status": tenant.status,
			"last_login": last_login,
			"days_quiet": quiet,
			"active_30": active_30,
			"seats": f"{cint(tenant.active_users)}/{cint(tenant.user_quota)}",
			"documents_30": documents,
			"unused_modules": ", ".join(unused) or _("none"),
			"verdict": _verdict(quiet, active_30, documents, unused),
		})
	rows.sort(key=lambda r: (-(r["days_quiet"] or 9999)))
	return rows


#: The doctype that stands in for each module having been used at all.
MODULE_PROBES = {
	"Solar CRM": "Solar Consumer",
	"Solar Operations": "Solar Installation",
	"Solar Projects": "Solar OM Contract",
}

#: What counts as activity in the last 30 days.
ACTIVITY_DOCTYPES = ("Solar Consumer", "Site Survey", "Solar Design Estimate",
                     "Solar Proposal", "Solar Installation", "Service Ticket")


def _counts_by_company(companies, cutoff):
	"""({company: {doctype: recent}}, {company: {doctype: total}}) in two queries each."""
	recent, ever = {}, {}
	for doctype in set(ACTIVITY_DOCTYPES) | set(MODULE_PROBES.values()):
		if not frappe.db.exists("DocType", doctype):
			continue
		for row in frappe.get_all(
			doctype, filters={"company": ["in", companies]},
			fields=["company", "count(name) as n"], group_by="company",
		):
			ever.setdefault(row["company"], {})[doctype] = cint(row["n"])
		if doctype not in ACTIVITY_DOCTYPES:
			continue
		for row in frappe.get_all(
			doctype,
			filters={"company": ["in", companies], "creation": [">=", cutoff]},
			fields=["company", "count(name) as n"], group_by="company",
		):
			recent.setdefault(row["company"], {})[doctype] = cint(row["n"])
	return recent, ever


def _unused_from(totals):
	"""A module with no records at all, not merely a quiet one."""
	return [module for module, doctype in MODULE_PROBES.items() if not totals.get(doctype)]


def _verdict(quiet, active_30, documents, unused):
	if quiet is None:
		return _("nobody has ever signed in")
	if quiet > 45:
		return _("silent for {0} days - this account is leaving").format(quiet)
	if active_30 == 0:
		return _("no logins in 30 days - call before the renewal, not after")
	if documents == 0:
		return _("people sign in but nothing is being created - they are not using it for work")
	if unused:
		return _("healthy, but paying for {0} they have never opened").format(
			", ".join(unused))
	return _("healthy")


