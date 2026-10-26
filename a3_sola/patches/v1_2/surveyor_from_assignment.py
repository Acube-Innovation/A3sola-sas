# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A survey's surveyor is the person its site survey was assigned to: each survey with no
surveyor takes theirs from the customer's site-survey to-do.
"""

import frappe

from a3_sola.api.survey_assignment import assigned_surveyor


def execute():
	for row in frappe.get_all("Site Survey", filters={"surveyor": ["in", ("", None)], "solar_consumer": ["is", "set"]},
			fields=["name", "solar_consumer"]):
		who = assigned_surveyor(row.solar_consumer)
		if who:
			frappe.db.set_value("Site Survey", row.name, "surveyor", who, update_modified=False)
