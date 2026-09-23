# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Lead: the outreach funnel, moved out of the client's spreadsheet."""

import frappe
from frappe import _

from a3_sola.api import outreach


def validate(doc, method=None):
	outreach.apply_outreach_state(doc)
	check_district_in_state(doc)
	pull_consumer_number(doc)


def check_district_in_state(doc):
	"""A district has to belong to the state chosen beside it.

	The form only offers the right districts, but a form is not the only way in - an
	import or an API call can set both fields freely - so the pairing is checked here,
	where every write passes.
	"""
	if not doc.meta.get_field("district") or not doc.get("district"):
		return
	state = frappe.db.get_value("Indian District", doc.district, "state")
	if not doc.get("state"):
		# Nothing to disagree with: take the district's own state.
		doc.state = state
		return
	if state and state != doc.state:
		frappe.throw(
			_("{0} is in {1}, not {2}.").format(doc.district, state, doc.state),
			title=_("District does not match the state"),
		)


def pull_consumer_number(doc):
	"""Copy the consumer number from the lead's own consumer.

	Once a lead has become a consumer, the consumer record holds the number the DISCOM
	issued and the lead should agree with it rather than keep whatever was typed during
	the enquiry. Only from a consumer that points back at this lead: a consumer linked by
	mistake, or one belonging to somebody else, must not write its number onto this lead.

	Runs on every save, so a number corrected on the consumer reaches the lead too.
	"""
	consumer = doc.get("solar_consumer")
	if not consumer or not doc.meta.get_field("consumer_number"):
		return
	row = frappe.db.get_value(
		"Solar Consumer", consumer, ["lead", "consumer_number"], as_dict=True
	)
	if not row or row.lead != doc.name:
		return
	if row.consumer_number and row.consumer_number != doc.get("consumer_number"):
		doc.consumer_number = row.consumer_number


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
