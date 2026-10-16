# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A consumer's installation site and permanent address are typed on the consumer, part by
part: house, street, city, district, state and PIN.

A consumer with an Address record takes that record's parts as its site, and is taken to
live there. One without stays blank and is asked for both on its next save. Each saved
consumer is then composed through its own controller, so the whole-address text is the
one a save would write; nothing else is re-validated.
"""

import frappe

from a3_sola.solar_crm.doctype.solar_consumer.solar_consumer import ADDRESS_PARTS, address_parts


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_consumer")
	for name in frappe.get_all("Solar Consumer", pluck="name"):
		doc = frappe.get_doc("Solar Consumer", name)
		if doc.installation_address and not doc.site_address_line1:
			for part, value in address_parts(doc.installation_address).items():
				if value:
					doc.set(f"site_{part}", value)
		if doc.permanent_address_same != "No":
			doc.permanent_address_same = "Yes"
			for part in ADDRESS_PARTS:
				doc.set(f"permanent_{part}", doc.get(f"site_{part}"))
		values = {f"{prefix}_{part}": doc.get(f"{prefix}_{part}") for prefix in ("site", "permanent") for part in ADDRESS_PARTS}
		values.update(
			permanent_address_same=doc.permanent_address_same,
			installation_site_address=doc.compose_address("site"),
			permanent_address=doc.compose_address("permanent"),
		)
		frappe.db.set_value("Solar Consumer", name, values, update_modified=False)
