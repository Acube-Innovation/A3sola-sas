# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Give existing DISCOM records the legal identity the agreement recites.

The net-metering agreement names the licensee as its second party - legal name, the Act it
was incorporated under, registered office. Those are properties of the licensee, not of any
one agreement, so they belong on the DISCOM record and are typed once. The fields are new,
so every DISCOM created before now is blank and the agreement would recite its record id.

Only KSEB is filled in, because only KSEB's particulars are known here. Any other DISCOM
gets its `discom_name` as the legal name and nothing else, which is honest: a blank office
prints as a blank line for someone to complete, whereas a guessed one prints as a fact.
"""

import frappe

KSEB = {
	"legal_name": "Kerala State Electricity Board Limited",
	"incorporation_recital": (
		"a company incorporated under the Indian Companies Act, 1956 (Central Act 1 of 1956)"
	),
	"registered_office": "Vydyuthi Bhavanam, Pattom, Thiruvananthapuram",
}


def execute():
	if not frappe.db.has_column("DISCOM", "legal_name"):
		return None
	filled = 0
	for row in frappe.get_all("DISCOM", fields=["name", "discom_name", "legal_name"]):
		if row.legal_name:
			continue
		values = dict(KSEB) if (row.discom_name or "").upper().startswith("KSEB") else {
			"legal_name": row.discom_name
		}
		frappe.db.set_value("DISCOM", row.name, values, update_modified=False)
		filled += 1
	frappe.db.commit()
	print(f"a3_sola: legal identity filled on {filled} DISCOM records")
	return filled
