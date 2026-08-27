# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Scheme Obligation Compliance.

One row per scheme-mandated contract, showing every obligation the client's registration
depends on. A vendor that fails to resolve complaints or maintain the performance ratio can
be temporarily deactivated, so this is a compliance record first and a management report
second - it is what the client would put in front of the implementing agency.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Solar OM Contract", "width": 150},
		{"label": _("Consumer"), "fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "width": 150},
		{"label": _("Scheme"), "fieldname": "subsidy_scheme", "fieldtype": "Link", "options": "Subsidy Scheme", "width": 170},
		{"label": _("Visit Compliance %"), "fieldname": "visit_compliance_percent", "fieldtype": "Percent", "width": 160},
		{"label": _("Missed Visits"), "fieldname": "missed_visits", "fieldtype": "Int", "width": 120},
		{"label": _("SLA Breaches"), "fieldname": "sla_breaches", "fieldtype": "Int", "width": 130},
		{"label": _("Open Tickets"), "fieldname": "open_tickets", "fieldtype": "Int", "width": 120},
		{"label": _("Current PR"), "fieldname": "current_performance_ratio_percent", "fieldtype": "Percent", "width": 120},
		{"label": _("Obligation"), "fieldname": "performance_obligation_status", "fieldtype": "Data", "width": 120},
		{"label": _("At Risk"), "fieldname": "at_risk", "fieldtype": "Check", "width": 90},
	]


def get_data(filters):
	contracts = frappe.get_list(
		"Solar OM Contract",
		filters={"company": filters.company, "docstatus": 1, "is_scheme_mandated": 1},
		fields=[
			"name", "solar_consumer", "solar_installation", "visit_compliance_percent",
			"open_tickets", "current_performance_ratio_percent", "performance_obligation_status",
		],
		limit_page_length=0,
	)
	for contract in contracts:
		contract["subsidy_scheme"] = frappe.db.get_value(
			"Solar Installation", contract.solar_installation, "subsidy_scheme"
		)
		contract["missed_visits"] = frappe.db.count(
			"Solar OM Visit Plan",
			{"parent": contract.name, "parenttype": "Solar OM Contract", "status": "Missed"},
		)
		contract["sla_breaches"] = frappe.db.count(
			"Service Ticket",
			{"om_contract": contract.name, "docstatus": 1, "resolution_sla_met": 0,
			 "status": ["in", ["Resolved", "Closed"]]},
		)
		contract["at_risk"] = (
			1
			if (
				contract.performance_obligation_status == "Breached"
				or contract["missed_visits"]
				or contract["sla_breaches"]
				or flt(contract.visit_compliance_percent) < 100
			)
			else 0
		)
	contracts.sort(key=lambda c: (-c["at_risk"], flt(c["visit_compliance_percent"])))
	if contracts:
		contracts.append(_portfolio(contracts))
	return contracts


def _portfolio(rows):
	"""The enforcement framework acts on a vendor, not on a job.

	So the portfolio line is the one that matters: a client with 95% compliance across
	forty roofs is in a different position from one with two breached out of three, and
	nobody reading a per-contract list arrives at that number by eye.
	"""
	live = [row for row in rows]
	count = len(live)
	breached = sum(1 for row in live if row["performance_obligation_status"] == "Breached")
	return {
		"name": None,
		"solar_consumer": None,
		"subsidy_scheme": _("PORTFOLIO ({0} scheme-mandated contracts)").format(count),
		"visit_compliance_percent": flt(
			sum(flt(row["visit_compliance_percent"]) for row in live) / count, 2
		),
		"missed_visits": sum(row["missed_visits"] for row in live),
		"sla_breaches": sum(row["sla_breaches"] for row in live),
		"open_tickets": sum(int(row["open_tickets"] or 0) for row in live),
		"current_performance_ratio_percent": flt(
			sum(flt(row["current_performance_ratio_percent"]) for row in live) / count, 2
		),
		"performance_obligation_status": _("{0} breached").format(breached),
		"at_risk": 1 if any(row["at_risk"] for row in live) else 0,
	}
