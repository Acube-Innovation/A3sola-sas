# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Payment Failure Analysis.

Ranked by revenue at risk rather than by count: fifty failed trial payments matter less
than three failed annual renewals, and a list sorted by frequency hides that.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api import dunning


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Error Code"), "fieldname": "error_code", "fieldtype": "Data", "width": 190},
		{"label": _("Class"), "fieldname": "error_class", "fieldtype": "Data", "width": 110},
		{"label": _("Method"), "fieldname": "method", "fieldtype": "Data", "width": 110},
		{"label": _("Failures"), "fieldname": "failures", "fieldtype": "Int", "width": 100},
		{"label": _("Revenue at Risk"), "fieldname": "value", "fieldtype": "Currency", "width": 160},
		{"label": _("Recovered After Dunning"), "fieldname": "recovered", "fieldtype": "Int", "width": 200},
		{"label": _("Recovery %"), "fieldname": "recovery_rate", "fieldtype": "Percent", "width": 130},
		{"label": _("What It Means"), "fieldname": "meaning", "fieldtype": "Data", "width": 260},
	]


def get_data(filters):
	policy = frappe.db.get_value("Dunning Policy", {"is_default": 1}, "name")
	policy_doc = frappe.get_cached_doc("Dunning Policy", policy) if policy else None

	rows = frappe.get_all(
		"Payment Transaction",
		filters={"status": "Failed"},
		fields=["error_code", "method", "amount", "payment_order"],
		limit_page_length=0,
	)
	grouped = {}
	for row in rows:
		key = (row.error_code or _("Not Reported"), row.method or _("Unknown"))
		bucket = grouped.setdefault(
			key,
			{"error_code": key[0], "method": key[1], "failures": 0, "value": 0.0,
			 "recovered": 0},
		)
		bucket["failures"] += 1
		bucket["value"] += flt(row.amount)
		# Recovered means the same order ended up paid despite this attempt failing.
		if frappe.db.get_value("Payment Order", row.payment_order, "status") == "Paid":
			bucket["recovered"] += 1

	out = []
	for bucket in grouped.values():
		error_class, _needs, message = dunning.classify_error(bucket["error_code"], policy_doc)
		bucket["error_class"] = error_class
		bucket["meaning"] = message or (
			_("Worth retrying.") if error_class == "Transient"
			else _("Not worth retrying - the customer must set up a new method.")
			if error_class == "Permanent"
			else _("Unclassified. Map this code on the Dunning Policy.")
		)
		bucket["recovery_rate"] = (
			flt(bucket["recovered"] * 100.0 / bucket["failures"], 2)
			if bucket["failures"] else 0.0
		)
		bucket["value"] = flt(bucket["value"], 2)
		out.append(bucket)
	out.sort(key=lambda r: r["value"], reverse=True)
	return out
