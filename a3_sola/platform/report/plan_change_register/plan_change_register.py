# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Plan Change Register.

Upgrades, downgrades, cycle switches and seat changes with the proration each produced and
the mandate consequence each carried. The mandate column is the one to scan: a row saying
anything other than None is a collection that will fail unless somebody acted on it.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Request"), "fieldname": "name", "fieldtype": "Dynamic Link", "options": "doctype", "width": 145},
		{"label": _("Type"), "fieldname": "doctype", "fieldtype": "Data", "width": 150},
		{"label": _("Change"), "fieldname": "change", "fieldtype": "Data", "width": 130},
		{"label": _("Tenant"), "fieldname": "tenant", "fieldtype": "Link", "options": "Tenant", "width": 140},
		{"label": _("From"), "fieldname": "from_plan", "fieldtype": "Data", "width": 150},
		{"label": _("To"), "fieldname": "to_plan", "fieldtype": "Data", "width": 150},
		{"label": _("Effective"), "fieldname": "effective_type", "fieldtype": "Data", "width": 100},
		{"label": _("Date"), "fieldname": "effective_date", "fieldtype": "Date", "width": 100},
		{"label": _("Prorated"), "fieldname": "net_amount_payable", "fieldtype": "Currency", "width": 115},
		{"label": _("New Recurring"), "fieldname": "new_recurring_amount", "fieldtype": "Currency", "width": 125},
		{"label": _("Mandate Impact"), "fieldname": "mandate_impact", "fieldtype": "Data", "width": 165},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 150},
	]


def get_data(filters):
	rows = []
	for change in frappe.get_all(
		"Plan Change Request", filters={"docstatus": ["<", 2]},
		fields=["name", "tenant", "request_type", "current_plan", "new_plan",
		        "effective_type", "effective_date", "net_amount_payable",
		        "new_recurring_amount", "mandate_impact", "status"],
		order_by="creation desc",
	):
		rows.append({
			"name": change.name, "doctype": "Plan Change Request",
			"change": change.request_type, "tenant": change.tenant,
			"from_plan": change.current_plan, "to_plan": change.new_plan,
			"effective_type": change.effective_type, "effective_date": change.effective_date,
			"net_amount_payable": flt(change.net_amount_payable),
			"new_recurring_amount": flt(change.new_recurring_amount),
			"mandate_impact": change.mandate_impact, "status": change.status,
		})
	for seat in frappe.get_all(
		"Seat Change Request", filters={"docstatus": ["<", 2]},
		fields=["name", "tenant", "change_type", "seat_delta", "current_quota",
		        "new_quota", "effective_type", "net_amount_payable",
		        "new_recurring_amount", "mandate_impact", "status", "applied_on"],
		order_by="creation desc",
	):
		rows.append({
			"name": seat.name, "doctype": "Seat Change Request",
			"change": _("{0} seat(s)").format(cint(seat.seat_delta)),
			"tenant": seat.tenant,
			"from_plan": _("{0} seats").format(cint(seat.current_quota)),
			"to_plan": _("{0} seats").format(cint(seat.new_quota)),
			"effective_type": seat.effective_type, "effective_date": seat.applied_on,
			"net_amount_payable": flt(seat.net_amount_payable),
			"new_recurring_amount": flt(seat.new_recurring_amount),
			"mandate_impact": seat.mandate_impact, "status": seat.status,
		})
	rows.sort(key=lambda r: str(r.get("effective_date") or ""), reverse=True)
	return rows
