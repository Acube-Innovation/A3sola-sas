# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Three phase is required above 5 kW, not 3 kW: the seeded KSERC phase rule moves to 5 kW,
its name and the clause the proposals print with it. A rule someone has already set to
another figure is left as it is. Its code stays, as the seed finds the rule by it."""

import frappe


def execute():
	for name, clause in frappe.get_all(
		"Grid Regulation Rule",
		filters={"rule_code": "KSERC-3PH-ABOVE-3KW", "threshold_kw": 3},
		fields=["name", "customer_facing_clause"],
		as_list=True,
	):
		frappe.db.set_value(
			"Grid Regulation Rule",
			name,
			{
				"threshold_kw": 5,
				"rule_name": "Three-phase connection required above 5 kW",
				"customer_facing_clause": (clause or "").replace("above 3 kW", "above 5 kW"),
			},
		)
