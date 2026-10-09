# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Lead, Solar Consumer and Site Survey point at each other.

The consumer names its lead and the lead its consumer, whichever side held the link; the
survey names its lead, from its consumer; the lead and the consumer name their latest
survey. Written directly, so no record is re-validated or re-dated by the migration.
"""

import frappe

from a3_sola.api.record_links import latest_survey


def execute():
	from a3_sola.setup.install import install_custom_fields

	frappe.reload_doc("solar_crm", "doctype", "solar_consumer")
	frappe.reload_doc("solar_crm", "doctype", "site_survey")
	install_custom_fields()  # Lead.site_survey

	# Consumer <-> lead, from whichever side has it.
	for lead, consumer in frappe.get_all("Lead", filters={"solar_consumer": ["is", "set"]},
			fields=["name", "solar_consumer"], as_list=True):
		if frappe.db.exists("Solar Consumer", consumer) and not frappe.db.get_value("Solar Consumer", consumer, "lead"):
			frappe.db.set_value("Solar Consumer", consumer, "lead", lead, update_modified=False)
	for consumer, lead in frappe.get_all("Solar Consumer", filters={"lead": ["is", "set"]},
			fields=["name", "lead"], as_list=True):
		if frappe.db.exists("Lead", lead) and not frappe.db.get_value("Lead", lead, "solar_consumer"):
			frappe.db.set_value("Lead", lead, "solar_consumer", consumer, update_modified=False)

	# Survey -> lead, from its consumer.
	for survey, consumer in frappe.get_all("Site Survey", filters={"lead": ["is", "not set"]},
			fields=["name", "solar_consumer"], as_list=True):
		lead = frappe.db.get_value("Solar Consumer", consumer, "lead") if consumer else None
		if lead:
			frappe.db.set_value("Site Survey", survey, "lead", lead, update_modified=False)

	# Lead and consumer -> their latest survey.
	for consumer, lead in frappe.get_all("Solar Consumer", fields=["name", "lead"], as_list=True):
		survey = latest_survey(consumer)
		frappe.db.set_value("Solar Consumer", consumer, "site_survey", survey, update_modified=False)
		if lead and frappe.db.exists("Lead", lead):
			frappe.db.set_value("Lead", lead, "site_survey", survey, update_modified=False)
