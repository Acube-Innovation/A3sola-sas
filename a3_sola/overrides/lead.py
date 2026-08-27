# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Lead: the outreach funnel, moved out of the client's spreadsheet."""

import frappe
from frappe import _

from a3_sola.api import outreach


def validate(doc, method=None):
	outreach.apply_outreach_state(doc)


@frappe.whitelist()
def create_solar_consumer(lead):
	"""Map a Lead's solar fields into a new Solar Consumer and link it back."""
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	if doc.get("solar_consumer"):
		frappe.throw(
			_("Lead {0} is already linked to {1}.").format(
				doc.name, frappe.utils.get_link_to_form("Solar Consumer", doc.solar_consumer)
			)
		)
	if not doc.get("discom"):
		frappe.throw(_("Set the DISCOM on the lead before creating a Solar Consumer."))

	consumer = frappe.get_doc(
		{
			"doctype": "Solar Consumer",
			"company": doc.company or frappe.defaults.get_user_default("Company"),
			"consumer_name": doc.lead_name,
			"mobile_no": doc.mobile_no or doc.phone,
			"email_id": doc.email_id,
			"consumer_category": doc.get("consumer_category") or "Residential",
			"discom": doc.discom,
			"discom_section": doc.get("discom_section"),
			"consumer_number": doc.get("consumer_number"),
			"connection_type": doc.get("connection_type"),
			"roof_type": doc.get("roof_type"),
			"avg_consumption_units": doc.get("approx_consumption_units"),
			"avg_bill_amount": doc.get("avg_monthly_bill"),
			"billing_frequency": "Bimonthly",
			"lead": doc.name,
		}
	).insert(ignore_permissions=True)

	doc.db_set("solar_consumer", consumer.name, update_modified=False)
	return consumer.name
