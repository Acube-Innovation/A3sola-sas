# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Dated regulatory constraints.

The KSERC regulation notified on 06.11.2025 requires plants above 3 kW to be three-phase,
and the High Court stayed it until 22.05.2026. Which of those is in force on a given date
changes both the sizing rule and the sentence that prints on the proposal - so it is data
with effective, stayed-from and stayed-until dates, never an if-statement.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from a3_sola.api.lookup import resolve


def _in_force(rule, on_date):
	"""A rule is in force when it has commenced and no stay covers the date."""
	if rule.effective_from and getdate(rule.effective_from) > on_date:
		return False
	if not rule.is_stayed:
		return True
	start = getdate(rule.stayed_from) if rule.stayed_from else None
	end = getdate(rule.stayed_until) if rule.stayed_until else None
	if start and on_date < start:
		return True
	if end and on_date > end:
		return True
	return False


@frappe.whitelist()
def get_active_rules(discom=None, on_date=None, company=None):
	"""Every Grid Regulation Rule in force on a date, with its stay resolved."""
	on_date = getdate(on_date or today())
	discom = resolve("DISCOM", discom) or discom
	filters = {}
	if company:
		filters["company"] = company

	names = frappe.get_all("Grid Regulation Rule", filters=filters, pluck="name")
	active = []
	for name in names:
		rule = frappe.get_cached_doc("Grid Regulation Rule", name)
		if rule.discom and discom and rule.discom != discom:
			continue
		if _in_force(rule, on_date):
			active.append(rule)
	return active


@frappe.whitelist()
def check_connection_type(capacity_kw, connection_type, discom=None, on_date=None, company=None) -> dict:
	"""Is this capacity allowed on this connection type today?

	Returns {"compliant", "required_type", "rule", "message", "stayed"}. While a stay is in
	force the answer is compliant with the stay named in the message, so a court order
	does not silently fail every quotation.
	"""
	capacity_kw = flt(capacity_kw)
	on_date = getdate(on_date or today())
	discom = resolve("DISCOM", discom) or discom
	result = {"compliant": True, "required_type": None, "rule": None, "message": "", "stayed": False}

	filters = {"rule_type": "Phase Requirement"}
	if company:
		filters["company"] = company
	names = frappe.get_all("Grid Regulation Rule", filters=filters, pluck="name")

	for name in names:
		rule = frappe.get_cached_doc("Grid Regulation Rule", name)
		if rule.discom and discom and rule.discom != discom:
			continue
		if not rule.threshold_kw or capacity_kw <= flt(rule.threshold_kw):
			continue
		if not _in_force(rule, on_date):
			result["stayed"] = True
			result["rule"] = rule.name
			result["message"] = _(
				"{0} would require a {1} connection above {2} kW, but it is stayed by {3} until {4}."
			).format(
				rule.rule_name,
				rule.required_connection_type,
				rule.threshold_kw,
				rule.stay_authority or _("order"),
				rule.stayed_until or _("further notice"),
			)
			continue
		if rule.required_connection_type and connection_type != rule.required_connection_type:
			result["compliant"] = False
			result["required_type"] = rule.required_connection_type
			result["rule"] = rule.name
			result["message"] = _("{0}: a {1} plant above {2} kW must be {3}.").format(
				rule.rule_name, capacity_kw, rule.threshold_kw, rule.required_connection_type
			)
			return result

	return result


@frappe.whitelist()
def get_customer_clauses(discom=None, on_date=None, company=None):
	"""The proposal clauses for the rules in force, rendered from the rules themselves."""
	return [
		{"rule": r.name, "clause": r.customer_facing_clause}
		for r in get_active_rules(discom, on_date, company)
		if r.customer_facing_clause
	]
