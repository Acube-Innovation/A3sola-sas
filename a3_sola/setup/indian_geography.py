# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""States and districts of India, as records a person can pick from a dropdown.

A lead's location has to be chosen, not typed, or the same district arrives spelled three
ways and no report groups. So the two live as masters rather than as a Select: a Select
would need a code change to correct, and district boundaries move - Andhra Pradesh went
from 13 districts to 26 in 2022, Ladakh separated from Jammu and Kashmir in 2019. As
records, the client fixes them without waiting for a release.

The data ships in `a3_sola/data/indian_states_districts.json`. It is a starting point and
not a legal register: it predates several recent reorganisations, and district names carry
no official code, so treat it as something to correct rather than something to trust.

Idempotent: a state or district that already exists is left exactly as it is, so a name
the client corrected is never written back over by a later run.
"""

import json
import os

import frappe

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data",
                    "indian_states_districts.json")

#: The one state this client works in, so a new lead starts where most leads are.
DEFAULT_STATE = "Kerala"


def _rows():
	with open(DATA, encoding="utf-8") as handle:
		return json.load(handle)


def install():
	"""Create every state and district that is not already on file."""
	if not frappe.db.exists("DocType", "Indian State"):
		return {"states": 0, "districts": 0, "skipped": "doctypes not installed"}

	states = districts = 0
	for row in _rows():
		if not frappe.db.exists("Indian State", row["state"]):
			doc = frappe.get_doc({
				"doctype": "Indian State",
				"state_name": row["state"],
				"state_code": row.get("state_code") or None,
				"is_union_territory": row.get("is_union_territory") or 0,
			})
			doc.flags.ignore_permissions = True
			doc.insert(ignore_permissions=True)
			states += 1

		for district in row["districts"]:
			name = "{0}, {1}".format(district, row["state"])
			if frappe.db.exists("Indian District", name):
				continue
			doc = frappe.get_doc({
				"doctype": "Indian District",
				"district_name": district,
				"state": row["state"],
			})
			doc.flags.ignore_permissions = True
			doc.insert(ignore_permissions=True)
			districts += 1

	frappe.db.commit()
	return {"states": states, "districts": districts}


def district_of(state, district_name):
	"""The district record for a plain district name within a state, or None."""
	if not state or not district_name:
		return None
	name = "{0}, {1}".format(district_name, state)
	return name if frappe.db.exists("Indian District", name) else None
