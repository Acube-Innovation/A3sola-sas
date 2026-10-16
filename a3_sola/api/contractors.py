# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A job's two contractors.

The mounting structure is erected by one contractor and the plant wired, installed and
certified by another - or by the same one doing both. The job (Solar Installation) names
each once, and the documents that go to a contractor start from the right one: a Structure
work order from the structure contractor; an Installation or rectification order, the
material dispatch notice and the completion certificate from the electrical contractor.
A contractor chosen on a document by hand is kept.
"""

import frappe

STRUCTURE = "structure"
ELECTRICAL = "electrical"

#: Which of the job's contractors a work order of each kind goes to.
ROLE_OF_KIND = {"Structure": STRUCTURE, "Installation": ELECTRICAL, "Rectification": ELECTRICAL}


def contractor_for(installation, role):
	"""The job's structure or electrical contractor, or None."""
	if not installation:
		return None
	return frappe.db.get_value("Solar Installation", installation, f"{role}_contractor") or None


def for_work_order(installation, kind):
	"""The contractor a work order of `kind` on this job goes to, or None."""
	role = ROLE_OF_KIND.get(kind)
	return contractor_for(installation, role) if role else None


def fill(doc, role, field="solar_contractor"):
	"""Give `doc` the job's contractor for `role` while its own field is blank."""
	if not doc.get(field):
		doc.set(field, contractor_for(doc.get("solar_installation"), role))
