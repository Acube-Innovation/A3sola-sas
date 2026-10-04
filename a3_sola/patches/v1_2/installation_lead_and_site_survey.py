# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every installation names its lead and site survey, and shows them on its Details tab.

Existing jobs are submitted, so neither the new mandatory lead nor the fetched Details
fields would ever be filled by a save. They are read back from the records each job already
links and written directly. The consumer name and number were fetched before this and are
left as they are: generated documents were issued against them.
"""

import frappe

from a3_sola.api import installation_lead
from a3_sola.setup.install import install_custom_fields

SOURCES = (
	"lead", "solar_consumer", "site_survey", "subsidy_eligibility_check",
	"solar_proposal", "solar_design_estimate", "quotation",
)
UNTOUCHED = {"consumer_name", "consumer_number"}


def execute():
	frappe.reload_doc("solar_operations", "doctype", "solar_installation")
	# `loan_required` on the Lead is fetched below, and custom fields are otherwise only
	# installed after the patches have run.
	install_custom_fields()
	meta = frappe.get_meta("Solar Installation")
	fetched = [
		df.fieldname for link in SOURCES for df in meta.get_fields_to_fetch(link)
		if df.fieldname not in UNTOUCHED
	]

	for name in frappe.get_all("Solar Installation", pluck="name"):
		doc = frappe.get_doc("Solar Installation", name)
		if not doc.lead:
			doc.lead = installation_lead.lead_of(
				doc.solar_consumer, doc.solar_design_estimate, doc.solar_proposal
			)
		if doc.lead and not doc.site_survey:
			doc.site_survey = installation_lead.lead_context(doc.lead, doc.solar_consumer).get("site_survey")
		doc.refresh_fetched(SOURCES)
		frappe.db.set_value(
			"Solar Installation", name,
			{field: doc.get(field) for field in ("lead", "site_survey", *fetched)},
			update_modified=False,
		)
