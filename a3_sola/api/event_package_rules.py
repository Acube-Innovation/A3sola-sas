# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Administration > Event Packages: which package an event visitor gets, by their bill and answers.

Each company keeps a list of rules (Event Package Rule), checked in order. A rule names a
range of the two-month electricity bill and, for each of the form's questions - property,
system, electricity connection, PM Surya Ghar subsidy - "Any" or one answer ("Not sure" is the
visitor leaving it blank). The first active rule that matches gives the package the instant
estimate (api/instant_estimate) quotes, and so the event proposal. With no rule matching, or a
rule's package that cannot be priced, the package is chosen automatically as before.

A rule overrides the event's own estimate packages (Solar Event.estimate_packages). A 1-month
bill is doubled before it is compared, as the estimate does.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from a3_sola.api.portal_users import require_admin

ROUTE = "/a3solaportal/event-packages"
DOCTYPE = "Event Package Rule"
ANY = "Any"
NOT_SURE = "Not sure"
#: The questions a rule can ask about, as (field, label).
QUESTIONS = (
	("interest", "Property"),
	("system_type", "System"),
	("connection_type", "Electricity connection"),
	("subsidy_option", "PM Surya Ghar subsidy"),
)
FIELDS = ["name", "rule_order", "is_active", "bill_from", "bill_to", "package"] + [q for q, _l in QUESTIONS]


def choices():
	"""{field: [Any, ...the form's answers]}: what each question of a rule may be."""
	from a3_sola.api.instant_estimate import CONNECTION_TYPES, SUBSIDY_OPTIONS
	from a3_sola.setup.custom_fields import INTEREST, SYSTEM_TYPE

	def opts(values):
		values = [v for v in values if v and v != NOT_SURE]
		return [ANY] + values + [NOT_SURE]

	return {
		# Property is required on the form: never "Not sure".
		"interest": [ANY] + INTEREST.split("\n"),
		"system_type": opts(SYSTEM_TYPE.split("\n")),
		"connection_type": opts(CONNECTION_TYPES),
		"subsidy_option": opts(SUBSIDY_OPTIONS),
	}


# ------------------------------------------------------------------ matching
def _answer_matches(wanted, given):
	wanted = wanted or ANY
	if wanted == ANY:
		return True
	given = (given or "").strip()
	if wanted == NOT_SURE:
		return given in ("", NOT_SURE)
	return given == wanted


def rules(company, active_only=False):
	filters = {"company": company}
	if active_only:
		filters["is_active"] = 1
	return frappe.get_all(DOCTYPE, filters=filters, fields=FIELDS, order_by="rule_order asc, creation asc")


def match(company, cycle_bill, interest=None, system_type=None, connection_type=None, subsidy_option=None):
	"""The first active rule of the company that the two-month bill and answers match, or None."""
	if not company or not frappe.db.table_exists(DOCTYPE):
		return None
	bill = flt(cycle_bill)
	given = {"interest": interest or "Home", "system_type": system_type,
		"connection_type": connection_type, "subsidy_option": subsidy_option}
	for rule in rules(company, active_only=True):
		if bill < flt(rule.bill_from) or (flt(rule.bill_to) and bill > flt(rule.bill_to)):
			continue
		if all(_answer_matches(rule.get(q), given[q]) for q, _l in QUESTIONS):
			return rule
	return None


# ------------------------------------------------------------------ the page
def companies():
	"""The companies this admin may set rules for."""
	from a3_sola.api.permissions import get_permitted_companies

	allowed = get_permitted_companies(frappe.session.user)
	if allowed is None:
		allowed = frappe.get_all("Company", pluck="name", order_by="name asc")
	return allowed


def default_company(allowed):
	from a3_sola.api.memberships import active_company

	for company in (active_company(), frappe.defaults.get_user_default("Company"),
			frappe.defaults.get_global_default("company")):
		if company and company in allowed:
			return company
	return allowed[0] if allowed else None


def _company(company):
	allowed = companies()
	company = company or default_company(allowed)
	if not company or company not in allowed:
		frappe.throw(_("You cannot set event packages for {0}.").format(company or _("this company")),
			frappe.PermissionError, title=_("Not Permitted"))
	return company


def packages(company, keep=()):
	"""The company's active packages a rule may name (and any a rule already names), smallest first."""
	rows = frappe.get_all("Solar Package", filters={"company": company},
		fields=["name", "package_name", "capacity_kw", "connection_type", "system_type", "is_dcr_compliant", "is_active", "status"],
		order_by="capacity_kw asc, package_name asc")
	out = []
	for p in rows:
		active = cint(p.is_active) and (p.status or "Active") == "Active"
		if not active and p.name not in keep:
			continue
		label = " · ".join(x for x in (
			"{0:g} kW".format(flt(p.capacity_kw)), p.connection_type, p.system_type,
			"DCR" if cint(p.is_dcr_compliant) else "Non-DCR", p.package_name or p.name) if x)
		out.append({"value": p.name, "label": label + ("" if active else " (inactive)")})
	return out


def page_data(company=None):
	allowed = companies()
	company = company if company in allowed else default_company(allowed)
	current = rules(company) if company else []
	return {
		"company": company,
		"companies": allowed,
		"rules": [dict(r, bill_from=flt(r.bill_from), bill_to=flt(r.bill_to) or None, is_active=cint(r.is_active))
			for r in current],
		"packages": packages(company, {r.package for r in current}) if company else [],
		"choices": choices(),
		"questions": [{"field": q, "label": label} for q, label in QUESTIONS],
	}


@frappe.whitelist()
def load(company=None):
	"""The page's data for another company. Admins only."""
	require_admin()
	return page_data(_company(company))


@frappe.whitelist(methods=["POST"])
def save(company, rows):
	"""Replace the company's rules with `rows`, in their order: [{bill_from, bill_to, interest,
	system_type, connection_type, subsidy_option, package, is_active}]. Admins only."""
	require_admin()
	company = _company(company)
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	opts = choices()
	allowed = {p["value"] for p in packages(company, {r.package for r in rules(company)})}
	clean = []
	for i, row in enumerate(rows or [], 1):
		label = _("Rule {0}").format(i)
		package = (row.get("package") or "").strip()
		if not package:
			frappe.throw(_("{0}: choose the package.").format(label), title=_("Package"))
		if package not in allowed:
			frappe.throw(_("{0}: {1} is not an active package of {2}.").format(label, package, company), title=_("Package"))
		bill_from, bill_to = flt(row.get("bill_from")), flt(row.get("bill_to"))
		if bill_from < 0 or bill_to < 0:
			frappe.throw(_("{0}: a bill amount cannot be below zero.").format(label), title=_("Bill Range"))
		if bill_to and bill_to < bill_from:
			frappe.throw(_("{0}: Bill to is below Bill from.").format(label), title=_("Bill Range"))
		values = {"bill_from": bill_from, "bill_to": bill_to or None, "package": package,
			"is_active": 1 if cint(row.get("is_active", 1)) else 0, "rule_order": i}
		for q, q_label in QUESTIONS:
			answer = (row.get(q) or ANY).strip()
			if answer not in opts[q]:
				frappe.throw(_("{0}: {1} is not a choice for {2}.").format(label, answer, q_label), title=_("Check the Rule"))
			values[q] = answer
		clean.append(values)

	for name in frappe.get_all(DOCTYPE, filters={"company": company}, pluck="name"):
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)
	for values in clean:
		frappe.get_doc(dict(values, doctype=DOCTYPE, company=company)).insert(ignore_permissions=True)
	return {"saved": len(clean), "data": page_data(company)}


@frappe.whitelist(methods=["POST"])
def check(company, data):
	"""What an event visitor with these answers would be shown: the instant estimate and the rule
	that chose its package, if any. Admins only."""
	require_admin()
	company = _company(company)
	data = frappe.parse_json(data) if isinstance(data, str) else (data or {})
	from a3_sola.api import instant_estimate

	bill = flt(data.get("bill_amount"))
	if bill <= 0:
		frappe.throw(_("Enter the bill amount."), title=_("Bill"))
	months = 1 if cint(data.get("bill_months")) == 1 else 2
	answers = {q: (data.get(q) or "").strip() or None for q, _l in QUESTIONS}
	answers["interest"] = answers["interest"] or "Home"
	est = instant_estimate.estimate(company, bill, months, answers["interest"], None, answers["system_type"],
		answers["connection_type"], answers["subsidy_option"])
	rule_no = cint(frappe.db.get_value(DOCTYPE, est["rule"], "rule_order")) or None if est and est.get("rule") else None
	return {"estimate": est, "rule_no": rule_no, "two_month_bill": bill * 2 / months,
		"summary": instant_estimate.summary(est) if est else ""}
