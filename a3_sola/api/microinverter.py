# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A micro-inverter system has no DCDB: each panel's inverter takes its DC on the roof, so
there is no DC to combine. Its DCDB count is 0 wherever a job's parts are counted - the
design estimate, the proposal and quotation, the project and its procurement list - and the
papers mark the micro inverter with an asterisk that says so."""

import re

import frappe

MICROINVERTER = "Microinverter"
NOTE = "* For micro inverter, DCDB is not required."
_DCDB = re.compile(r"\bDCDB\b", re.IGNORECASE)


def is_micro(row):
	"""Whether an inverter row (estimate, installation or package) is a micro inverter."""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	return bool(row.get("inverter_type")) and technology_name(row.get("inverter_type")) == MICROINVERTER


def uses_microinverter(doc):
	"""Whether the inverter a design or a project is priced with is a micro inverter - its
	alternates shown for choice (`is_option`) do not count."""
	if isinstance(doc, str):
		doc = frappe.get_doc("Solar Installation", doc)
	return any(is_micro(r) for r in doc.get("inverters") or [] if not r.get("is_option"))


def is_dcdb(name):
	"""A BOS item or BOM line that is the DCDB ("DCDB", "1/1 DCDB Strider Mersen SPD")."""
	return bool(name and _DCDB.search(name))
