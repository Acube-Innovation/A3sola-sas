# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""AFA Exposure.

When the RBI revises the no-authentication ceiling - and it has, repeatedly - this report
tells the client exactly which customers change category and which are close enough to
matter. That question is otherwise unanswerable without a database query.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api.settings import get_float

#: Within this much of the ceiling counts as "one upgrade away from changing route".
MARGIN_PERCENT = 15.0


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Subscription"), "fieldname": "name", "fieldtype": "Link", "options": "Platform Subscription", "width": 160},
		{"label": _("Organisation"), "fieldname": "organisation_name", "fieldtype": "Data", "width": 200},
		{"label": _("Plan"), "fieldname": "plan_code", "fieldtype": "Data", "width": 110},
		{"label": _("Cycle"), "fieldname": "billing_cycle", "fieldtype": "Data", "width": 90},
		{"label": _("Recurring Debit"), "fieldname": "recurring_amount", "fieldtype": "Currency", "width": 150},
		{"label": _("Ceiling"), "fieldname": "ceiling", "fieldtype": "Currency", "width": 130},
		{"label": _("Headroom"), "fieldname": "headroom", "fieldtype": "Currency", "width": 130},
		{"label": _("Route"), "fieldname": "collection_route", "fieldtype": "Data", "width": 150},
		{"label": _("Near the Ceiling"), "fieldname": "near_ceiling", "fieldtype": "Check", "width": 150},
		{"label": _("Mandate Covers It"), "fieldname": "mandate_covers", "fieldtype": "Data", "width": 160},
	]


def get_data(filters):
	ceiling = flt(filters.get("ceiling") or get_float("afa_free_debit_ceiling", 15000.0))
	margin = ceiling * MARGIN_PERCENT / 100.0

	rows = frappe.get_all(
		"Platform Subscription",
		filters={"docstatus": 1},
		fields=[
			"name", "organisation_name", "plan_code", "billing_cycle",
			"recurring_amount", "collection_route", "payment_mandate",
		],
		limit_page_length=0,
	)
	for row in rows:
		amount = flt(row.recurring_amount)
		row["ceiling"] = ceiling
		row["headroom"] = flt(ceiling - amount, 2)
		row["near_ceiling"] = 1 if 0 <= row["headroom"] <= margin else 0
		row["mandate_covers"] = _mandate_state(row.payment_mandate, amount)
		row.pop("payment_mandate", None)
	rows.sort(key=lambda r: r["headroom"])
	return rows


def _mandate_state(mandate, amount):
	if not mandate:
		return _("No mandate")
	row = frappe.db.get_value(
		"Payment Mandate", mandate, ["status", "registered_max_amount"], as_dict=True
	)
	if not row:
		return _("No mandate")
	if row.status != "Active":
		return _("Mandate {0}").format(row.status)
	if flt(amount) > flt(row.registered_max_amount):
		# A silent future failure. This is what the report exists to catch.
		return _("Above the authorised {0}").format(
			frappe.utils.fmt_money(row.registered_max_amount, currency="INR")
		)
	return _("Yes")
